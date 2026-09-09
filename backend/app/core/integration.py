"""Shared integration outcomes, safe errors, timeouts, and retry policy."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Optional, TypeVar

from .references import ExternalReference


T = TypeVar("T")
_MAX_SAFE_MESSAGE_LENGTH = 500
_SECRET_KEY = (
    r"(?:authorization|proxy[_ -]?authorization|credentials?|password|secret|token|"
    r"api[_ -]?key|private[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"client[_ -]?secret|webhook[_ -]?secret|smtp[_ -]?password|mqtt[_ -]?password)"
)
_QUOTED_SECRET_ASSIGNMENT = re.compile(
    rf"(?i)([\"']?{_SECRET_KEY}[\"']?\s*[:=]\s*)([\"'])(.*?)\2"
)
_UNQUOTED_SECRET_ASSIGNMENT = re.compile(
    rf"(?i)([\"']?{_SECRET_KEY}[\"']?\s*[:=]\s*)(?![\"'])([^\s,;}}\]]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)\b((?:proxy[_ -]?)?authorization\s*[:=]\s*)([^,;]+)"
)
_URL_USERINFO = re.compile(r"(://)[^/@\s]+@")


def sanitize_integration_message(
    message: object,
    *,
    secret_values: tuple[str, ...] = (),
) -> str:
    """Remove common credential forms from a bounded diagnostic message."""

    safe = str(message).replace("\r", " ").replace("\n", " ")
    for secret in secret_values:
        if secret:
            safe = safe.replace(secret, "[REDACTED]")
    safe = _AUTHORIZATION_VALUE.sub(
        lambda match: f"{match.group(1)}[REDACTED]",
        safe,
    )
    safe = _BEARER_TOKEN.sub("Bearer [REDACTED]", safe)
    safe = _QUOTED_SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(2)}",
        safe,
    )
    safe = _UNQUOTED_SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}[REDACTED]",
        safe,
    )
    safe = _URL_USERINFO.sub(r"\1[REDACTED]@", safe)
    return safe[:_MAX_SAFE_MESSAGE_LENGTH]


class IntegrationStatus(str, Enum):
    SUCCEEDED = "succeeded"
    ACCEPTED = "accepted"
    SIMULATED = "simulated"
    PENDING = "pending"
    RETRYING = "retrying"
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IntegrationFailure:
    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        code = self.code.strip().lower().replace(" ", "_")
        if not code:
            raise ValueError("integration failure code must not be empty")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", sanitize_integration_message(self.message))


@dataclass(frozen=True, slots=True)
class IntegrationResult(Generic[T]):
    """Normalized, secret-free result returned by provider boundaries."""

    provider: str
    operation: str
    status: IntegrationStatus
    value: Optional[T] = field(default=None, repr=False)
    external_reference: Optional[ExternalReference] = field(default=None, repr=False)
    failure: Optional[IntegrationFailure] = None
    attempts: int = 1

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.operation.strip():
            raise ValueError("provider and operation must not be empty")
        if self.attempts < 1:
            raise ValueError("attempts must include the first call")
        failed = self.status in {
            IntegrationStatus.FAILED,
            IntegrationStatus.NOT_CONFIGURED,
            IntegrationStatus.RETRYING,
        }
        if failed != (self.failure is not None):
            raise ValueError("failure details must match the integration status")

    @property
    def ok(self) -> bool:
        return self.status in {
            IntegrationStatus.SUCCEEDED,
            IntegrationStatus.ACCEPTED,
            IntegrationStatus.SIMULATED,
        }

    @property
    def terminal(self) -> bool:
        return self.status not in {
            IntegrationStatus.PENDING,
            IntegrationStatus.RETRYING,
        }

    @classmethod
    def succeeded(
        cls,
        *,
        provider: str,
        operation: str,
        value: Optional[T] = None,
        external_reference: Optional[ExternalReference] = None,
        attempts: int = 1,
    ) -> "IntegrationResult[T]":
        return cls(
            provider=provider,
            operation=operation,
            status=IntegrationStatus.SUCCEEDED,
            value=value,
            external_reference=external_reference,
            attempts=attempts,
        )

    @classmethod
    def accepted(
        cls,
        *,
        provider: str,
        operation: str,
        value: Optional[T] = None,
        external_reference: Optional[ExternalReference] = None,
        attempts: int = 1,
    ) -> "IntegrationResult[T]":
        return cls(
            provider=provider,
            operation=operation,
            status=IntegrationStatus.ACCEPTED,
            value=value,
            external_reference=external_reference,
            attempts=attempts,
        )

    @classmethod
    def simulated(
        cls,
        *,
        provider: str,
        operation: str,
        value: Optional[T] = None,
    ) -> "IntegrationResult[T]":
        return cls(
            provider=provider,
            operation=operation,
            status=IntegrationStatus.SIMULATED,
            value=value,
        )

    @classmethod
    def pending(
        cls,
        *,
        provider: str,
        operation: str,
        value: Optional[T] = None,
        external_reference: Optional[ExternalReference] = None,
    ) -> "IntegrationResult[T]":
        return cls(
            provider=provider,
            operation=operation,
            status=IntegrationStatus.PENDING,
            value=value,
            external_reference=external_reference,
        )

    @classmethod
    def failed(
        cls,
        *,
        provider: str,
        operation: str,
        failure: IntegrationFailure,
        attempts: int = 1,
        status: IntegrationStatus = IntegrationStatus.FAILED,
    ) -> "IntegrationResult[T]":
        if status not in {
            IntegrationStatus.FAILED,
            IntegrationStatus.NOT_CONFIGURED,
            IntegrationStatus.RETRYING,
        }:
            raise ValueError("failed result requires a failure status")
        return cls(
            provider=provider,
            operation=operation,
            status=status,
            failure=failure,
            attempts=attempts,
        )


class IntegrationError(RuntimeError):
    """Base provider error whose string representation is safe to log."""

    default_code = "integration_error"
    retryable = False

    def __init__(
        self,
        *,
        provider: str,
        operation: str,
        message: object,
        code: Optional[str] = None,
        retryable: Optional[bool] = None,
        retry_after_seconds: Optional[float] = None,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        self.provider = provider.strip().lower()
        self.operation = operation.strip().lower()
        self.code = (code or self.default_code).strip().lower()
        if retryable is not None:
            self.retryable = retryable
        self.safe_message = sanitize_integration_message(
            message,
            secret_values=secret_values,
        )
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"{self.provider}.{self.operation} [{self.code}]: {self.safe_message}"
        )

    def as_failure(self) -> IntegrationFailure:
        return IntegrationFailure(
            code=self.code,
            message=self.safe_message,
            retryable=self.retryable,
            retry_after_seconds=self.retry_after_seconds,
        )


class IntegrationConfigurationError(IntegrationError):
    default_code = "not_configured"


class IntegrationAuthenticationError(IntegrationError):
    default_code = "authentication_failed"


class IntegrationValidationError(IntegrationError):
    default_code = "invalid_request"


class IntegrationTimeoutError(IntegrationError):
    default_code = "timeout"
    retryable = True


class IntegrationUnavailableError(IntegrationError):
    default_code = "unavailable"
    retryable = True


class IntegrationRateLimitError(IntegrationError):
    default_code = "rate_limited"
    retryable = True


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    connect_seconds: float = 5.0
    read_seconds: float = 30.0
    write_seconds: float = 30.0
    pool_seconds: float = 5.0

    def __post_init__(self) -> None:
        if min(
            self.connect_seconds,
            self.read_seconds,
            self.write_seconds,
            self.pool_seconds,
        ) <= 0:
            raise ValueError("integration timeouts must be positive")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry convention for idempotent provider operations."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.5
    multiplier: float = 2.0
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must include the first call")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays must be non-negative")
        if self.multiplier < 1:
            raise ValueError("retry multiplier must be at least 1")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max retry delay must not be below the initial delay")

    def delay_after(self, attempts_made: int, *, retry_after_seconds: float | None = None) -> float:
        """Return the bounded delay after a failed attempt."""

        if attempts_made < 1:
            raise ValueError("attempts_made must be positive")
        calculated = self.initial_delay_seconds * (self.multiplier ** (attempts_made - 1))
        requested = retry_after_seconds if retry_after_seconds is not None else calculated
        return min(max(requested, 0.0), self.max_delay_seconds)

    def allows_retry(
        self,
        *,
        attempts_made: int,
        failure: IntegrationFailure,
        operation_is_idempotent: bool,
        idempotency_key: str | None = None,
    ) -> bool:
        """Never retry side-effecting writes unless they carry a dedupe key."""

        safe_to_repeat = operation_is_idempotent or bool(idempotency_key)
        return failure.retryable and safe_to_repeat and attempts_made < self.max_attempts


__all__ = [
    "IntegrationAuthenticationError",
    "IntegrationConfigurationError",
    "IntegrationError",
    "IntegrationFailure",
    "IntegrationRateLimitError",
    "IntegrationResult",
    "IntegrationStatus",
    "IntegrationTimeoutError",
    "IntegrationUnavailableError",
    "IntegrationValidationError",
    "RetryPolicy",
    "TimeoutPolicy",
    "sanitize_integration_message",
]
