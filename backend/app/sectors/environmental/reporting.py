"""Environmental-owned enrichment adapter for the common report engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset
from app.modules.reports.ports import report_context_registry
from app.sectors.environmental.domain import SECTOR
from app.sectors.environmental.services import environmental_report_context


class EnvironmentalReportContextProvider:
    sector = SECTOR

    def build(self, db: Session, asset: Asset) -> Mapping[str, Any]:
        return environmental_report_context(db, asset=asset)


environmental_report_context_provider = EnvironmentalReportContextProvider()


def register_environmental_report_context() -> None:
    report_context_registry.register(environmental_report_context_provider)


__all__ = [
    "EnvironmentalReportContextProvider",
    "environmental_report_context_provider",
    "register_environmental_report_context",
]
