"""Mining-owned enrichment adapter for the common report engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset
from app.modules.reports.ports import report_context_registry
from app.sectors.mining.domain import SECTOR
from app.sectors.mining.services import mining_report_context


class MiningReportContextProvider:
    sector = SECTOR

    def build(self, db: Session, asset: Asset) -> Mapping[str, Any]:
        return mining_report_context(db, asset=asset)


mining_report_context_provider = MiningReportContextProvider()


def register_mining_report_context() -> None:
    report_context_registry.register(mining_report_context_provider)


__all__ = [
    "MiningReportContextProvider",
    "mining_report_context_provider",
    "register_mining_report_context",
]
