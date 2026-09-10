"""Composition-owned synchronization for enabled sector definitions."""

from sqlalchemy.orm import Session

from app.sectors.agriculture.services import sync_kpi_definitions as sync_agriculture_kpis
from app.sectors.infrastructure.services import (
    sync_kpi_definitions as sync_infrastructure_kpis,
)


def sync_enabled_sector_definitions(db: Session) -> None:
    sync_agriculture_kpis(db)
    sync_infrastructure_kpis(db)
    db.commit()


__all__ = ["sync_enabled_sector_definitions"]
