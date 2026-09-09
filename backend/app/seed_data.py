"""Seed data helpers for the GeoVision store."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.core import database
from app.core.config import settings
from app.core.passwords import hash_password, validate_admin_password


def seed_admin_users() -> int:
    """Create admin user(s) if they do not exist.

    The admin password MUST be set via the ADMIN_PASSWORD environment
    variable.  If it is not set, admin seeding is skipped with a warning.
    """
    admin_password = (settings.admin_password or "").strip()
    admin_emails = settings.admin_email_list
    if not admin_password or not admin_emails:
        print(
            "[GeoVision] WARNING: ADMIN_PASSWORD or ADMIN_EMAILS not set — "
            "skipping admin seed."
        )
        return 0
    validate_admin_password(admin_password)

    db: Session = database.SessionLocal()
    inserted = 0
    try:
        for email in admin_emails:
            exists = (
                db.query(models.User)
                .filter(func.lower(func.trim(models.User.email)) == email)
                .first()
            )
            if exists:
                if exists.role != "admin":
                    raise RuntimeError(
                        "configured admin address belongs to a non-admin user; "
                        "use an audited identity grant instead of email promotion"
                    )
                assignment = (
                    db.query(models.InternalRoleAssignment)
                    .filter(
                        models.InternalRoleAssignment.user_id == exists.id,
                        models.InternalRoleAssignment.role == "GV_SUPER_ADMIN",
                    )
                    .one_or_none()
                )
                if assignment is None:
                    db.add(
                        models.InternalRoleAssignment(
                            user_id=exists.id,
                            role="GV_SUPER_ADMIN",
                        )
                    )
                continue

            user = models.User(
                email=email,
                password_hash=hash_password(admin_password),
                role="admin",
            )
            db.add(user)
            db.flush()
            db.add(
                models.InternalRoleAssignment(
                    user_id=user.id,
                    role="GV_SUPER_ADMIN",
                )
            )
            inserted += 1

        db.commit()
        return inserted
    finally:
        db.close()
