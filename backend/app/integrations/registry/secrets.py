"""Secret-reference policy and fail-closed registry secret stores."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
import re
from threading import RLock
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlsplit


_VAULT_HOST_PATTERN = re.compile(
    r"^(?=.{3,24}\.vault\.azure\.net$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.vault\.azure\.net$"
)
_SECRET_NAME_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,127}$")
_SECRET_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,128}$")
_MAX_SECRET_VALUE_BYTES = 64 * 1024


class SecretStoreHealthState(str, Enum):
    UNAVAILABLE = "unavailable"
    CONFIGURED = "configured"
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class SecretStoreHealth:
    provider: str
    state: SecretStoreHealthState
    configured: bool
    available: bool
    reason_code: str


class InvalidSecretReference(ValueError):
    """Raised without echoing a rejected URI."""

    def __init__(self) -> None:
        super().__init__("invalid Azure Key Vault secret reference")


class SecretStoreError(RuntimeError):
    """Base safe error for secret-resolution policy."""


class SecretStoreUnavailable(SecretStoreError):
    pass


class SecretNotFound(SecretStoreError):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class KeyVaultSecretReference:
    """Validated internal reference; repr/str never reveal its URI or secret name."""

    vault_url: str = field(repr=False)
    secret_name: str = field(repr=False)
    version: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return "<KeyVaultSecretReference redacted=True>"

    __str__ = __repr__

    def _cache_key(self) -> str:
        version = f"/{self.version}" if self.version is not None else ""
        return f"{self.vault_url}/secrets/{self.secret_name}{version}"


@dataclass(frozen=True, slots=True, repr=False)
class SecretValue:
    """An explicitly revealable value whose ordinary representations are redacted."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self._value, str) or not self._value:
            raise ValueError("resolved secret value must be non-empty text")
        if len(self._value.encode("utf-8")) > _MAX_SECRET_VALUE_BYTES:
            raise ValueError("resolved secret value is too large")

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "<SecretValue redacted=True>"

    __str__ = __repr__


def parse_key_vault_secret_reference(uri: object) -> KeyVaultSecretReference:
    """Accept only canonical Azure public-cloud HTTPS secret URIs."""

    if not isinstance(uri, str) or not uri or len(uri) > 512 or uri != uri.strip():
        raise InvalidSecretReference()
    try:
        parsed = urlsplit(uri)
        port = parsed.port
    except (TypeError, ValueError):
        raise InvalidSecretReference() from None
    host = parsed.hostname
    if (
        parsed.scheme != "https"
        or host is None
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not _VAULT_HOST_PATTERN.fullmatch(host)
        or "%" in parsed.path
    ):
        raise InvalidSecretReference()
    # Explicit :443 and non-canonical host casing are rejected so one reference
    # has exactly one cache/audit identity.
    if parsed.netloc != host:
        raise InvalidSecretReference()
    segments = parsed.path.split("/")
    if len(segments) not in {3, 4} or segments[0] or segments[1] != "secrets":
        raise InvalidSecretReference()
    secret_name = segments[2]
    version = segments[3] if len(segments) == 4 else None
    if _SECRET_NAME_PATTERN.fullmatch(secret_name) is None:
        raise InvalidSecretReference()
    if version is not None and _SECRET_VERSION_PATTERN.fullmatch(version) is None:
        raise InvalidSecretReference()
    return KeyVaultSecretReference(
        vault_url=f"https://{host}",
        secret_name=secret_name,
        version=version,
    )


@runtime_checkable
class SecretStore(Protocol):
    def resolve(self, reference: str | KeyVaultSecretReference) -> SecretValue: ...

    def health(self) -> SecretStoreHealth: ...


def _reference(value: str | KeyVaultSecretReference) -> KeyVaultSecretReference:
    if isinstance(value, KeyVaultSecretReference):
        # Revalidate explicitly constructed dataclass instances before a vault
        # URL reaches the injected client factory.
        return parse_key_vault_secret_reference(value._cache_key())
    return parse_key_vault_secret_reference(value)


class NullSecretStore:
    """Default store which can never resolve a credential."""

    def resolve(self, reference: str | KeyVaultSecretReference) -> SecretValue:
        del reference
        raise SecretStoreUnavailable("secret store is not configured")

    def health(self) -> SecretStoreHealth:
        return SecretStoreHealth(
            provider="none",
            state=SecretStoreHealthState.UNAVAILABLE,
            configured=False,
            available=False,
            reason_code="secret_store_not_configured",
        )

    def __repr__(self) -> str:
        return "<NullSecretStore fail_closed=True>"


class InMemorySecretStore:
    """Deterministic, immutable fake for local and contract tests."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values: dict[str, SecretValue] = {}
        for raw_reference, raw_value in values.items():
            reference = parse_key_vault_secret_reference(raw_reference)
            self._values[reference._cache_key()] = SecretValue(raw_value)

    def resolve(self, reference: str | KeyVaultSecretReference) -> SecretValue:
        parsed = _reference(reference)
        value = self._values.get(parsed._cache_key())
        if value is None:
            raise SecretNotFound("secret was not found")
        return value

    def health(self) -> SecretStoreHealth:
        return SecretStoreHealth(
            provider="memory",
            state=SecretStoreHealthState.HEALTHY,
            configured=True,
            available=True,
            reason_code="deterministic_secret_store",
        )

    def __repr__(self) -> str:
        return f"<InMemorySecretStore entries={len(self._values)} redacted=True>"


class KeyVaultSecretBundle(Protocol):
    value: str | None


class KeyVaultSecretClient(Protocol):
    def get_secret(
        self,
        name: str,
        version: str | None = None,
        **kwargs: Any,
    ) -> KeyVaultSecretBundle: ...


class AzureKeyVaultSecretStore:
    """Adapter contract for an injected Azure ``SecretClient`` factory.

    The factory receives the validated vault URL.  This class never imports an
    SDK, creates credentials, lists secrets, or performs writes.
    """

    def __init__(
        self,
        client_factory: Callable[[str], KeyVaultSecretClient],
    ) -> None:
        if not callable(client_factory):
            raise TypeError("client_factory must be callable")
        self._client_factory = client_factory
        self._clients: dict[str, KeyVaultSecretClient] = {}
        self._attempted = False
        self._last_failed = False
        self._lock = RLock()

    def resolve(self, reference: str | KeyVaultSecretReference) -> SecretValue:
        parsed = _reference(reference)
        with self._lock:
            self._attempted = True
            client = self._clients.get(parsed.vault_url)
            try:
                if client is None:
                    client = self._client_factory(parsed.vault_url)
                    self._clients[parsed.vault_url] = client
            except Exception:
                self._last_failed = True
                raise SecretStoreUnavailable("secret resolution failed") from None
        try:
            # Do not serialize unrelated secret resolutions behind a network
            # timeout. Official Azure SecretClient instances are thread-safe.
            bundle = client.get_secret(parsed.secret_name, parsed.version)
            value = bundle.value
            resolved = SecretValue(value) if isinstance(value, str) else None
            if resolved is None:
                raise ValueError("secret response did not contain text")
        except Exception:
            # Azure exceptions may contain request URIs and identity details.
            with self._lock:
                self._last_failed = True
            raise SecretStoreUnavailable("secret resolution failed") from None
        with self._lock:
            self._last_failed = False
        return resolved

    def health(self) -> SecretStoreHealth:
        with self._lock:
            attempted = self._attempted
            failed = self._last_failed
        if failed:
            return SecretStoreHealth(
                provider="azure_key_vault",
                state=SecretStoreHealthState.DEGRADED,
                configured=True,
                available=False,
                reason_code="secret_resolution_failed",
            )
        if attempted:
            return SecretStoreHealth(
                provider="azure_key_vault",
                state=SecretStoreHealthState.HEALTHY,
                configured=True,
                available=True,
                reason_code="secret_resolution_succeeded",
            )
        return SecretStoreHealth(
            provider="azure_key_vault",
            state=SecretStoreHealthState.CONFIGURED,
            configured=True,
            available=False,
            reason_code="secret_store_not_probed",
        )

    def __repr__(self) -> str:
        return "<AzureKeyVaultSecretStore configured=True references=redacted>"


__all__ = [
    "AzureKeyVaultSecretStore",
    "InMemorySecretStore",
    "InvalidSecretReference",
    "KeyVaultSecretBundle",
    "KeyVaultSecretClient",
    "KeyVaultSecretReference",
    "NullSecretStore",
    "SecretNotFound",
    "SecretStore",
    "SecretStoreError",
    "SecretStoreHealth",
    "SecretStoreHealthState",
    "SecretStoreUnavailable",
    "SecretValue",
    "parse_key_vault_secret_reference",
]
