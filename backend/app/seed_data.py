"""Seed data helpers for the GeoVision store."""

from __future__ import annotations

import os
from typing import List

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.utils import hash_password


# Admin accounts — password read from ADMIN_PASSWORD env var (never hardcoded)
ADMIN_USERS: List[dict] = [
    {
        "email": "genovesi.maria@geovisionops.com",
        "role": "admin",
    },
]


def seed_admin_users() -> int:
    """Create admin user(s) if they do not exist.

    The admin password MUST be set via the ADMIN_PASSWORD environment
    variable.  If it is not set, admin seeding is skipped with a warning.
    """
    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not admin_password:
        print("[GeoVision] WARNING: ADMIN_PASSWORD env var not set — skipping admin seed.")
        return 0

    db: Session = SessionLocal()
    inserted = 0
    try:
        for user_data in ADMIN_USERS:
            exists = (
                db.query(models.User)
                .filter(models.User.email == user_data["email"])
                .first()
            )
            if exists:
                updated = False
                if not getattr(exists, "role", None):
                    exists.role = user_data.get("role", "admin")
                    updated = True
                if updated:
                    db.add(exists)
                continue

            db.add(
                models.User(
                    email=user_data["email"],
                    password_hash=hash_password(admin_password),
                    role=user_data.get("role", "admin"),
                )
            )
            inserted += 1

        db.commit()
        return inserted
    finally:
        db.close()
