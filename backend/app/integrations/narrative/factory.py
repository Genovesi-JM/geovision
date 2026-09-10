"""Narrative adapter composition with a safe offline default."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.modules.reports.ports import NarrativeProvider

from .deterministic import DeterministicNarrativeProvider
from .unavailable import UnavailableNarrativeProvider


def create_narrative_provider(
    config: Settings | None = None,
) -> NarrativeProvider:
    selected = config or settings
    provider = selected.report_narrative_provider
    if provider in {"deterministic", "mock"}:
        return DeterministicNarrativeProvider()
    # Azure-hosted generation is intentionally not guessed from generic AI
    # credentials. A dedicated adapter can replace this boundary only after
    # deployment credentials and model access are verified.
    return UnavailableNarrativeProvider(provider, selected.report_narrative_model)


__all__ = ["create_narrative_provider"]
