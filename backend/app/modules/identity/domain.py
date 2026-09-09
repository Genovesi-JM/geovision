"""Provider-neutral identity values exposed to GeoVision modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TokenUse(str, Enum):
    """A token's trusted purpose; callers must not infer this from its header."""

    INTERNAL_SESSION = "internal_session"
    API_ACCESS_TOKEN = "api_access_token"
    ID_TOKEN = "id_token"


@dataclass(frozen=True, slots=True)
class ExternalPrincipal:
    """A validated identity-provider principal with no raw token or claims."""

    provider: str
    identity_subject: str
    subject: str
    issuer: str
    origin_provider: Optional[str] = None
    tenant_id: Optional[str] = None
    object_id: Optional[str] = None
    internal_user_id: Optional[str] = None
    internal_auth_generation: Optional[int] = None
    email_hint: Optional[str] = None
    email_verified: bool = False
    display_name: Optional[str] = None
    scopes: frozenset[str] = field(default_factory=frozenset)
    roles: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for field_name in ("provider", "identity_subject", "subject", "issuer"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value.strip())

        for field_name in (
            "tenant_id",
            "object_id",
            "internal_user_id",
            "origin_provider",
            "email_hint",
            "display_name",
        ):
            value = getattr(self, field_name)
            if isinstance(value, str):
                normalized = value.strip()
                object.__setattr__(self, field_name, normalized or None)

        object.__setattr__(
            self,
            "scopes",
            frozenset(scope.strip() for scope in self.scopes if scope.strip()),
        )
        object.__setattr__(
            self,
            "roles",
            frozenset(role.strip() for role in self.roles if role.strip()),
        )
        if self.internal_auth_generation is not None and (
            isinstance(self.internal_auth_generation, bool)
            or not isinstance(self.internal_auth_generation, int)
            or self.internal_auth_generation < 0
        ):
            raise ValueError("internal_auth_generation must be non-negative")


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    """GeoVision authorization context built after local-user resolution."""

    user_id: str
    identity_subject: str
    active_workspace_id: Optional[str] = None
    active_organization_id: Optional[str] = None
    permissions: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, str) or not self.user_id.strip():
            raise ValueError("user_id must not be empty")
        if not isinstance(self.identity_subject, str) or not self.identity_subject.strip():
            raise ValueError("identity_subject must not be empty")
        object.__setattr__(self, "user_id", self.user_id.strip())
        object.__setattr__(self, "identity_subject", self.identity_subject.strip())
        object.__setattr__(
            self,
            "permissions",
            frozenset(
                permission.strip()
                for permission in self.permissions
                if permission.strip()
            ),
        )


__all__ = ["AuthorizationContext", "ExternalPrincipal", "TokenUse"]
