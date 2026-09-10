"""Composition-owned synchronization for enabled sector definitions."""

from sqlalchemy.orm import Session

from app.sectors.agriculture.services import (
    sync_kpi_definitions as sync_agriculture_kpis,
)
from app.sectors.environmental.services import (
    sync_kpi_definitions as sync_environmental_kpis,
)
from app.sectors.infrastructure.services import (
    sync_kpi_definitions as sync_infrastructure_kpis,
)
from app.sectors.mining.services import sync_kpi_definitions as sync_mining_kpis
from app.sectors.ports.services import sync_kpi_definitions as sync_ports_kpis


def sync_enabled_sector_definitions(db: Session) -> None:
    sync_agriculture_kpis(db)
    sync_infrastructure_kpis(db)
    sync_environmental_kpis(db)
    sync_mining_kpis(db)
    sync_ports_kpis(db)
    db.commit()


__all__ = ["sync_enabled_sector_definitions"]
