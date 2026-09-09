"""Public organization services used by compatibility transport layers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Company, CompanyUser, User


def get_user_company_id(user: User, db: Session) -> Optional[str]:
    """Resolve a user's legacy company and repair a missing membership link.

    The fallback write is existing behavior retained for compatibility. Phase 4
    will replace this split identity with the canonical workspace/RBAC model.
    """

    email = (user.email or "").strip().lower()
    company_user = db.query(CompanyUser).filter(CompanyUser.email == email).first()
    if company_user:
        return company_user.company_id

    company = db.query(Company).filter(Company.email == email).first()
    if company:
        db.add(
            CompanyUser(
                company_id=company.id,
                email=email,
                name=getattr(user, "full_name", None) or email,
                role="owner",
                is_active=True,
            )
        )
        db.commit()
        return company.id
    return None


__all__ = ["get_user_company_id"]
