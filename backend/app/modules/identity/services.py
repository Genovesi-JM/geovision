"""GeoVision user resolution, first-login provisioning, and auth context."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import AuthIdentity, User, UserProfile
from app.modules.identity.domain import AuthorizationContext, ExternalPrincipal
from app.modules.organizations.domain import (
    InternalRole,
    customer_permissions,
    internal_permissions,
)
from app.modules.organizations.services import (
    OrganizationAccessError,
    active_internal_roles,
    resolve_workspace_access,
)


_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class IdentityResolutionError(RuntimeError):
    """A stable, non-sensitive identity resolution failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    user: User
    identity: Optional[AuthIdentity]
    created: bool = False


def _canonical_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    email = value.strip().lower()
    if not email or any(character in email for character in "\r\n"):
        return None
    try:
        return str(_EMAIL_ADAPTER.validate_python(email)).lower()
    except (TypeError, ValidationError):
        return None


def _is_uuid(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def _user_for_canonical_email(db: Session, email: str) -> Optional[User]:
    matches = (
        db.query(User)
        .filter(func.lower(func.trim(User.email)) == email)
        .limit(2)
        .all()
    )
    if len(matches) > 1:
        raise IdentityResolutionError(
            "identity_conflict",
            "Multiple GeoVision users have the same normalized email",
        )
    return matches[0] if matches else None


def _ensure_profile(
    db: Session,
    user: User,
    display_name: Optional[str],
) -> UserProfile:
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(
            user_id=user.id,
            full_name=display_name,
            entity_type="individual",
        )
        db.add(profile)
    elif display_name and not profile.full_name:
        profile.full_name = display_name
        db.add(profile)
    return profile


class IdentityService:
    """Resolve trusted principals to immutable GeoVision user IDs."""

    def __init__(self, db: Session, config: Optional[Settings] = None):
        self.db = db
        self.config = config or settings

    def resolve_internal_principal(
        self,
        principal: ExternalPrincipal,
    ) -> ResolvedIdentity:
        if principal.provider != "internal":
            raise IdentityResolutionError(
                "wrong_identity_provider",
                "Expected an internal GeoVision session",
            )

        if not principal.internal_user_id or not _is_uuid(principal.internal_user_id):
            raise IdentityResolutionError(
                "invalid_internal_user_id",
                "Session user identifier is invalid",
            )
        # Both versioned and accepted legacy sessions must carry the immutable
        # internal UUID. Email-only sessions can attach to a replacement user
        # after deletion and are therefore never accepted.
        user = self.db.get(User, principal.internal_user_id)

        if user is None or not user.is_active:
            raise IdentityResolutionError(
                "inactive_or_missing_user",
                "GeoVision user is missing or inactive",
            )
        if principal.internal_auth_generation != user.auth_generation:
            raise IdentityResolutionError(
                "stale_authentication_generation",
                "GeoVision session has been superseded",
            )
        return ResolvedIdentity(user=user, identity=None)

    def resolve_external_principal(
        self,
        principal: ExternalPrincipal,
        *,
        provision: bool,
    ) -> ResolvedIdentity:
        if principal.provider == "internal":
            return self.resolve_internal_principal(principal)

        identity = (
            self.db.query(AuthIdentity)
            .filter(
                AuthIdentity.issuer == principal.issuer,
                AuthIdentity.subject == principal.subject,
            )
            .first()
        )
        if identity is None and principal.provider in {"google", "microsoft"}:
            # Safely upgrade a same-provider legacy row. Microsoft/Graph rows
            # are intentionally not bridged to Entra subjects without a
            # separately verified migration because their tenant is unknown.
            identity = (
                self.db.query(AuthIdentity)
                .filter(
                    AuthIdentity.provider == principal.provider,
                    AuthIdentity.provider_user_id == principal.subject,
                    AuthIdentity.issuer.is_(None),
                    AuthIdentity.subject.is_(None),
                )
                .first()
            )
            if identity is not None:
                identity.issuer = principal.issuer
                identity.subject = principal.subject
                identity.tenant_id = principal.tenant_id

        if identity is not None:
            user = self.db.get(User, identity.user_id)
            if user is None or not user.is_active:
                raise IdentityResolutionError(
                    "inactive_or_missing_user",
                    "GeoVision user is missing or inactive",
                )
            if principal.email_verified:
                identity.email = _canonical_email(principal.email_hint) or identity.email
            # A later token that omits this optional claim must not erase a
            # previously established verification signal.
            identity.email_verified = bool(identity.email_verified) or principal.email_verified
            identity.display_name = principal.display_name or identity.display_name
            identity.last_login_at = utc_now()
            self.db.add(identity)
            _ensure_profile(self.db, user, principal.display_name)
            try:
                self.db.commit()
            except IntegrityError as exc:
                self.db.rollback()
                raise IdentityResolutionError(
                    "identity_conflict",
                    "External identity mapping conflicts with an existing identity",
                ) from exc
            self.db.refresh(user)
            return ResolvedIdentity(user=user, identity=identity)

        if not provision:
            raise IdentityResolutionError(
                "identity_not_linked",
                "External identity is not linked to a GeoVision user",
            )

        email = _canonical_email(principal.email_hint)
        if email is None or not principal.email_verified:
            raise IdentityResolutionError(
                "verified_email_required",
                "A verified email is required for first login",
            )

        user = _user_for_canonical_email(self.db, email)
        if user is not None and not self.config.identity_auto_link_verified_email:
            raise IdentityResolutionError(
                "email_link_requires_confirmation",
                "This email already belongs to a GeoVision user",
            )
        created = user is None
        try:
            if user is None:
                user = User(
                    email=email,
                    password_hash=None,
                    role="cliente",
                    is_active=True,
                )
                self.db.add(user)
                # The unique email constraint can race; keep the flush inside
                # the guarded transaction so it becomes a stable conflict.
                self.db.flush()
            elif not user.is_active:
                raise IdentityResolutionError(
                    "inactive_or_missing_user",
                    "GeoVision user is missing or inactive",
                )

            identity = AuthIdentity(
                user_id=user.id,
                provider=principal.provider,
                provider_user_id=principal.subject,
                issuer=principal.issuer,
                subject=principal.subject,
                tenant_id=principal.tenant_id,
                email=email,
                email_verified=True,
                display_name=principal.display_name,
                # Deliberately do not persist raw identity-provider claims.
                raw_data=None,
                last_login_at=utc_now(),
            )
            self.db.add(identity)
            _ensure_profile(self.db, user, principal.display_name)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            winner = (
                self.db.query(AuthIdentity)
                .filter(
                    AuthIdentity.issuer == principal.issuer,
                    AuthIdentity.subject == principal.subject,
                )
                .first()
            )
            if winner is None:
                existing_email_user = _user_for_canonical_email(self.db, email)
                if existing_email_user is not None:
                    raise IdentityResolutionError(
                        "email_link_requires_confirmation",
                        "This email already belongs to a GeoVision user",
                    ) from exc
                raise IdentityResolutionError(
                    "identity_conflict",
                    "External identity could not be provisioned safely",
                ) from exc
            winner_user = self.db.get(User, winner.user_id)
            if winner_user is None or not winner_user.is_active:
                raise IdentityResolutionError(
                    "inactive_or_missing_user",
                    "GeoVision user is missing or inactive",
                ) from exc
            return ResolvedIdentity(user=winner_user, identity=winner)

        self.db.refresh(user)
        self.db.refresh(identity)
        return ResolvedIdentity(user=user, identity=identity, created=created)


def permissions_for_roles(
    global_role: Optional[str],
    workspace_role: Optional[str],
) -> frozenset[str]:
    """Compatibility wrapper around the canonical Phase 4 policy maps."""

    permissions = {"profile:read", *customer_permissions(workspace_role)}
    if (global_role or "").strip().lower() == "admin":
        permissions.update(internal_permissions({InternalRole.SUPER_ADMIN.value}))
    return frozenset(permissions)


def build_authorization_context(
    db: Session,
    user: User,
    principal: ExternalPrincipal,
    *,
    requested_workspace_id: Optional[str] = None,
) -> AuthorizationContext:
    try:
        access = resolve_workspace_access(
            db,
            user,
            requested_workspace_id=requested_workspace_id,
        )
    except OrganizationAccessError as exc:
        if requested_workspace_id or exc.code == "workspace_access_denied":
            raise IdentityResolutionError(
                "workspace_access_denied",
                "Requested workspace is not accessible",
            ) from exc
        staff_roles = active_internal_roles(db, user)
        return AuthorizationContext(
            user_id=user.id,
            identity_subject=principal.identity_subject,
            internal_roles=staff_roles,
            permissions=frozenset(
                {"profile:read", *internal_permissions(staff_roles)}
            ),
        )

    return AuthorizationContext(
        user_id=user.id,
        identity_subject=principal.identity_subject,
        active_workspace_id=(access.workspace.id if access.workspace else None),
        active_organization_id=access.organization.id,
        workspace_role=access.workspace_role,
        organization_role=access.organization_role,
        internal_roles=access.internal_roles,
        permissions=access.permissions,
    )


def issue_session_access_token(
    user: User,
    principal: Optional[ExternalPrincipal] = None,
    *,
    expires_delta: Optional[timedelta] = None,
    expires_at: Optional[datetime] = None,
) -> str:
    if (
        expires_delta is None
        and expires_at is None
        and principal is not None
        and (principal.origin_provider or principal.provider) != "internal"
    ):
        expires_delta = min(
            timedelta(minutes=settings.access_token_expires_minutes),
            timedelta(hours=settings.external_identity_session_max_hours),
        )
    return create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role or "cliente",
        identity_provider=(
            (principal.origin_provider or principal.provider)
            if principal
            else "internal"
        ),
        identity_issuer=principal.issuer if principal else None,
        identity_subject=principal.identity_subject if principal else None,
        auth_generation=user.auth_generation,
        expires_delta=expires_delta,
        expires_at=expires_at,
    )


__all__ = [
    "IdentityResolutionError",
    "IdentityService",
    "ResolvedIdentity",
    "build_authorization_context",
    "issue_session_access_token",
    "permissions_for_roles",
]
