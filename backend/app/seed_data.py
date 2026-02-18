"""Seed data helpers for the GeoVision store."""

from __future__ import annotations

import os
from typing import List

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.utils import hash_password

DEMO_PRODUCTS: List[dict] = [
    {
        "name": "NDVI + Pulverização 200 ha",
        "slug": "ndvi-pulverizacao-200",
        "category": "servico-drone",
        "sector": "agricultura",
        "description": "Missão completa com drone multiespectral + pulverização em precisão para 200 ha.",
        "price_cents": 245000,
        "unit_label": "por missão",
    },
    {
        "name": "Kit IoT Pecuária – 25 colares",
        "slug": "kit-iot-pecuaria-25",
        "category": "hardware-iot",
        "sector": "pecuaria",
        "description": "Colares inteligentes + gateway LoRaWAN para rastrear rebanhos em grandes extensões.",
        "price_cents": 189000,
        "unit_label": "por kit",
    },
    {
        "name": "Mapeamento LIDAR para mina",
        "slug": "mapeamento-lidar-mina",
        "category": "servico-lidar",
        "sector": "mining",
        "description": "Modelo 3D, volumes e perfis de talude com drone LIDAR de classe industrial.",
        "price_cents": 360000,
        "unit_label": "por campanha",
    },
    {
        "name": "Sensores estruturais para ponte",
        "slug": "sensores-ponte",
        "category": "hardware-sensor",
        "sector": "infra",
        "description": "Pacote de sensores de vibração, inclinação e temperatura integrados no dashboard GeoVision.",
        "price_cents": 275000,
        "unit_label": "por instalação",
    },
    {
        "name": "Ração mineralizada – 5t",
        "slug": "racao-mineralizada-5t",
        "category": "insumo-nutricao",
        "sector": "pecuaria",
        "description": "Formulação balanceada para suportar o rebanho durante a época seca.",
        "price_cents": 82000,
        "unit_label": "por lote",
    },
]


# Admin accounts — password read from ADMIN_PASSWORD env var (never hardcoded)
ADMIN_USERS: List[dict] = [
    {
        "email": "genovesi.maria@geovisionops.com",
        "role": "admin",
    },
]


def seed_demo_products() -> int:
    """Populate products if the table is empty.

    Returns:
        int: number of products inserted.
    """
    return 0


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
