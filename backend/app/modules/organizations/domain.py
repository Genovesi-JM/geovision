"""Organization, workspace, membership, and RBAC domain values."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class CustomerRole(str, Enum):
    """Customer-facing roles stored on organization/workspace memberships."""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"
    FINANCE = "finance"


class InternalRole(str, Enum):
    """GeoVision staff roles; never store these on customer memberships."""

    SUPER_ADMIN = "GV_SUPER_ADMIN"
    OPERATIONS = "GV_OPERATIONS"
    ANALYST = "GV_ANALYST"
    SUPPORT = "GV_SUPPORT"
    FINANCE = "GV_FINANCE"
    INVENTORY = "GV_INVENTORY"
    SALES = "GV_SALES"


class MembershipStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


CUSTOMER_ROLE_PERMISSIONS: dict[CustomerRole, frozenset[str]] = {
    CustomerRole.VIEWER: frozenset(
        {"organization:read", "workspace:read"}
    ),
    CustomerRole.MEMBER: frozenset(
        {
            "organization:read",
            "workspace:read",
            "workspace:contribute",
        }
    ),
    CustomerRole.FINANCE: frozenset(
        {
            "organization:read",
            "workspace:read",
            "billing:read",
            "billing:manage",
        }
    ),
    CustomerRole.MANAGER: frozenset(
        {
            "organization:read",
            "workspace:read",
            "workspace:contribute",
            "workspace:operate",
            "workspace:manage",
        }
    ),
    CustomerRole.ADMIN: frozenset(
        {
            "organization:read",
            "organization:manage",
            "organization:manage_members",
            "workspace:read",
            "workspace:contribute",
            "workspace:operate",
            "workspace:manage",
            "billing:read",
            "billing:manage",
        }
    ),
    CustomerRole.OWNER: frozenset(
        {
            "organization:read",
            "organization:manage",
            "organization:manage_members",
            "organization:transfer_ownership",
            "workspace:read",
            "workspace:contribute",
            "workspace:operate",
            "workspace:manage",
            "billing:read",
            "billing:manage",
        }
    ),
}


INTERNAL_ROLE_PERMISSIONS: dict[InternalRole, frozenset[str]] = {
    InternalRole.SUPER_ADMIN: frozenset(
        {
            "platform:admin",
            "operations:access",
            "support:access",
            "analytics:review",
            "billing:internal",
            "inventory:internal",
            "sales:internal",
        }
    ),
    InternalRole.OPERATIONS: frozenset({"operations:access"}),
    InternalRole.ANALYST: frozenset({"analytics:review"}),
    InternalRole.SUPPORT: frozenset({"support:access"}),
    InternalRole.FINANCE: frozenset({"billing:internal"}),
    InternalRole.INVENTORY: frozenset({"inventory:internal"}),
    InternalRole.SALES: frozenset({"sales:internal"}),
}


_LEGACY_CUSTOMER_ROLES = {
    "operator": CustomerRole.MANAGER,
    "client": CustomerRole.MEMBER,
    "cliente": CustomerRole.MEMBER,
    "customer": CustomerRole.MEMBER,
}


def normalize_customer_role(value: str | CustomerRole) -> CustomerRole:
    if isinstance(value, CustomerRole):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in _LEGACY_CUSTOMER_ROLES:
        return _LEGACY_CUSTOMER_ROLES[normalized]
    try:
        return CustomerRole(normalized)
    except ValueError as exc:
        allowed = ", ".join(role.value for role in CustomerRole)
        raise ValueError(f"Unsupported customer role; expected one of: {allowed}") from exc


def customer_permissions(value: str | CustomerRole | None) -> frozenset[str]:
    if value is None:
        return frozenset()
    try:
        role = normalize_customer_role(value)
    except ValueError:
        # Unknown historical roles fail closed instead of inheriting power.
        return frozenset()
    return CUSTOMER_ROLE_PERMISSIONS[role]


def internal_permissions(values: Iterable[str | InternalRole]) -> frozenset[str]:
    permissions: set[str] = set()
    for value in values:
        try:
            role = value if isinstance(value, InternalRole) else InternalRole(value)
        except ValueError:
            continue
        permissions.update(INTERNAL_ROLE_PERMISSIONS[role])
    return frozenset(permissions)


def permission_granted(permissions: Iterable[str], required: str) -> bool:
    available = frozenset(permissions)
    return required in available or "platform:admin" in available


__all__ = [
    "CUSTOMER_ROLE_PERMISSIONS",
    "INTERNAL_ROLE_PERMISSIONS",
    "CustomerRole",
    "InternalRole",
    "MembershipStatus",
    "WorkspaceStatus",
    "customer_permissions",
    "internal_permissions",
    "normalize_customer_role",
    "permission_granted",
]
