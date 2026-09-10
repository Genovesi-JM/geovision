"""Lazy processing-provider selection at the application composition edge."""

from __future__ import annotations

from app.core.config import Settings, settings
from app.modules.processing.ports import ProcessingProvider


def create_processing_provider(
    config: Settings = settings,
    provider_name: str | None = None,
) -> ProcessingProvider:
    name = (
        (provider_name or config.processing_provider).strip().lower().replace("-", "_")
    )
    if name in {"fake", "deterministic"}:
        if config.is_deployed:
            from .unavailable import UnavailableProcessingProvider

            return UnavailableProcessingProvider("fake")
        from .fake import DeterministicProcessingProvider

        return DeterministicProcessingProvider()
    if name in {"nodeodm", "opendronemap"}:
        from .nodeodm import NodeODMProcessingProvider

        return NodeODMProcessingProvider(config)
    if name in {
        "pix4d",
        "autodesk_reality_capture",
        "bentley_reality_modeling",
        "none",
        "null",
    }:
        from .unavailable import UnavailableProcessingProvider

        return UnavailableProcessingProvider(name)
    from .unavailable import UnavailableProcessingProvider

    return UnavailableProcessingProvider(name or "processing")


__all__ = ["create_processing_provider"]
