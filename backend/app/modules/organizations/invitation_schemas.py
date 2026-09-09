"""Public contracts for invitation acceptance and service-first onboarding."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.modules.organizations.domain import CustomerRole


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class InvitationTargetType(str, Enum):
    WORKSPACE = "workspace"
    ASSET = "asset"
    REPORT = "report"
    SERVICE_RESULT = "service_result"
    ORDER = "order"


class OnboardingIntent(str, Enum):
    REQUEST_SERVICE = "request_service"
    MONITOR_ASSET = "monitor_asset"
    BUY_PRODUCT = "buy_product"
    VIEW_INVITATION = "view_invitation"


INVITABLE_ROLES = frozenset(
    {
        CustomerRole.ADMIN,
        CustomerRole.MANAGER,
        CustomerRole.MEMBER,
        CustomerRole.VIEWER,
        CustomerRole.FINANCE,
    }
)


class InvitationCreate(BaseModel):
    organization_id: str = Field(min_length=1, max_length=36)
    workspace_id: str = Field(min_length=1, max_length=36)
    target_email: EmailStr
    intended_role: CustomerRole = CustomerRole.MEMBER
    identity_hint: Optional[str] = Field(default=None, max_length=200)
    target_type: InvitationTargetType = InvitationTargetType.WORKSPACE
    target_id: Optional[str] = Field(default=None, max_length=36)
    expires_in_hours: int = Field(default=168, ge=1, le=720)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("intended_role")
    @classmethod
    def prevent_owner_invitation(cls, value: CustomerRole) -> CustomerRole:
        if value not in INVITABLE_ROLES:
            raise ValueError(
                "owner access cannot be granted by invitation; use the authenticated ownership-transfer flow"
            )
        return value

    @model_validator(mode="after")
    def validate_target_identifier(self):
        if self.target_type is InvitationTargetType.WORKSPACE:
            if self.target_id not in (None, self.workspace_id):
                raise ValueError("workspace invitations must target the selected workspace")
        elif not self.target_id:
            raise ValueError("target_id is required for this invitation target")
        return self


class InvitationTokenRequest(BaseModel):
    token: str = Field(min_length=43, max_length=512)


class InvitationDestination(BaseModel):
    kind: InvitationTargetType
    organization_id: str
    workspace_id: str
    target_id: Optional[str] = None
    path: str


class InvitationOut(BaseModel):
    id: str
    organization_id: str
    workspace_id: str
    membership_id: str
    target_email: EmailStr
    identity_hint: Optional[str] = None
    intended_role: CustomerRole
    target_type: InvitationTargetType
    target_id: Optional[str] = None
    status: InvitationStatus
    invited_by_user_id: str
    accepted_by_user_id: Optional[str] = None
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    destination: InvitationDestination


class InvitationCreated(InvitationOut):
    token: str
    accept_url: str
    mobile_deep_link: str


class InvitationPreview(BaseModel):
    invitation_id: str
    organization_name: str
    workspace_name: str
    target_email_hint: str
    intended_role: CustomerRole
    status: InvitationStatus
    expires_at: datetime
    destination: InvitationDestination


class InvitationAcceptance(BaseModel):
    invitation: InvitationOut
    accepted: bool
    idempotent: bool


class OnboardingIntentOption(BaseModel):
    id: OnboardingIntent
    label: str
    description: str
    next_path: str
    requires_invitation: bool = False


class OnboardingIntentRequest(BaseModel):
    intent: OnboardingIntent
    invitation_token: Optional[str] = Field(default=None, min_length=43, max_length=512)

    @model_validator(mode="after")
    def require_invitation_token(self):
        if self.intent is OnboardingIntent.VIEW_INVITATION and not self.invitation_token:
            raise ValueError("invitation_token is required for view_invitation")
        if self.intent is not OnboardingIntent.VIEW_INVITATION and self.invitation_token:
            raise ValueError("invitation_token is only valid for view_invitation")
        return self


class OnboardingIntentResolution(BaseModel):
    intent: OnboardingIntent
    next_path: str
    onboarding_required: bool
    invitation_preview: Optional[InvitationPreview] = None


class OnboardingContext(BaseModel):
    onboarding_complete: bool
    pending_invitation_count: int
    organization_ids: list[str]
    workspace_ids: list[str]
    intents: list[OnboardingIntentOption]


__all__ = [
    "INVITABLE_ROLES",
    "InvitationAcceptance",
    "InvitationCreate",
    "InvitationCreated",
    "InvitationDestination",
    "InvitationOut",
    "InvitationPreview",
    "InvitationStatus",
    "InvitationTargetType",
    "InvitationTokenRequest",
    "OnboardingContext",
    "OnboardingIntent",
    "OnboardingIntentOption",
    "OnboardingIntentRequest",
    "OnboardingIntentResolution",
]
