"""Public organization services used by compatibility transport layers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import CompanyUser, User


def get_user_company_id(user: User, db: Session) -> Optional[str]:
    """Resolve a legacy company by immutable GeoVision user ID.

    Email-only rows remain non-authoritative until an audited migration or the
    canonical Phase 4 membership flow binds them to a user ID.
    """

    company_user = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.user_id == user.id,
            CompanyUser.is_active.is_(True),
        )
        .order_by(CompanyUser.created_at.asc())
        .first()
    )
    return company_user.company_id if company_user else None


__all__ = ["get_user_company_id"]
