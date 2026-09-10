"""Infrastructure-owned enrichment adapter for the common report engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset
from app.modules.reports.ports import report_context_registry
from app.sectors.infrastructure.domain import SECTOR
from app.sectors.infrastructure.services import infrastructure_report_context


class InfrastructureReportContextProvider:
    sector = SECTOR

    def build(self, db: Session, asset: Asset) -> Mapping[str, Any]:
        return infrastructure_report_context(db, asset=asset)


infrastructure_report_context_provider = InfrastructureReportContextProvider()


def register_infrastructure_report_context() -> None:
    report_context_registry.register(infrastructure_report_context_provider)


__all__ = [
    "InfrastructureReportContextProvider",
    "infrastructure_report_context_provider",
    "register_infrastructure_report_context",
]
