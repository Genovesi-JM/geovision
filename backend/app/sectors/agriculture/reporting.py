"""Agriculture-owned enrichment adapter for the common report engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset
from app.modules.reports.ports import report_context_registry
from app.sectors.agriculture.domain import SECTOR
from app.sectors.agriculture.services import agriculture_report_context


class AgricultureReportContextProvider:
    sector = SECTOR

    def build(self, db: Session, asset: Asset) -> Mapping[str, Any]:
        return agriculture_report_context(db, asset=asset)


agriculture_report_context_provider = AgricultureReportContextProvider()


def register_agriculture_report_context() -> None:
    report_context_registry.register(agriculture_report_context_provider)


__all__ = [
    "AgricultureReportContextProvider",
    "agriculture_report_context_provider",
    "register_agriculture_report_context",
]
