"""Ports-owned enrichment adapter for the common report engine."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import Asset
from app.modules.reports.ports import report_context_registry
from app.sectors.ports.domain import SECTOR
from app.sectors.ports.services import ports_report_context


class PortsReportContextProvider:
    sector = SECTOR

    def build(self, db: Session, asset: Asset) -> Mapping[str, Any]:
        return ports_report_context(db, asset=asset)


ports_report_context_provider = PortsReportContextProvider()


def register_ports_report_context() -> None:
    report_context_registry.register(ports_report_context_provider)


__all__ = [
    "PortsReportContextProvider",
    "ports_report_context_provider",
    "register_ports_report_context",
]
