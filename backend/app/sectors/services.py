"""Composition-owned synchronization for enabled sector definitions."""

from sqlalchemy.orm import Session

from app.sectors.agriculture.services import sync_kpi_definitions


def sync_enabled_sector_definitions(db: Session) -> None:
    sync_kpi_definitions(db)
    db.commit()


__all__ = ["sync_enabled_sector_definitions"]
