"""Provider contracts and sector-owned report context registry."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.models import Asset


class NarrativeProvider(Protocol):
    provider_name: str
    model_name: str | None

    def generate(self, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SectorReportContextProvider(Protocol):
    sector: str

    def build(self, db: Any, asset: Asset) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ReportContextRegistration:
    sector: str
    provider: SectorReportContextProvider


class ReportContextRegistry:
    """Keeps common reports independent from optional sector packages."""

    def __init__(self) -> None:
        self._providers: dict[str, SectorReportContextProvider] = {}

    def register(self, provider: SectorReportContextProvider) -> None:
        sector = str(provider.sector).strip().upper()
        if not sector:
            raise ValueError("sector report provider must declare a sector")
        existing = self._providers.get(sector)
        if existing is not None and existing is not provider:
            if existing.__class__ is provider.__class__:
                return
            raise ValueError(f"report context provider already registered for {sector}")
        self._providers[sector] = provider

    def get(self, sector: str) -> SectorReportContextProvider | None:
        return self._providers.get(str(sector or "").strip().upper())

    def sectors(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


report_context_registry = ReportContextRegistry()


__all__ = [
    "NarrativeProvider",
    "ReportContextRegistration",
    "ReportContextRegistry",
    "SectorReportContextProvider",
    "report_context_registry",
]
