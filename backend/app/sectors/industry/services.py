"""Application services for Industry, Energy and Utilities intelligence."""

from sqlalchemy.orm import Session

from app.modules.analytics.services import ensure_kpi_definition
from app.sectors.industry.domain import KPI_DEFINITIONS


def sync_kpi_definitions(db: Session) -> None:
    """Create or refresh every enabled Industry KPI definition."""

    for definition in KPI_DEFINITIONS:
        ensure_kpi_definition(db, definition)


__all__ = ["sync_kpi_definitions"]
