"""Metadata contract for optional sector packages."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SectorModule:
    """Declare a vertical's common-module needs without activating behavior."""

    name: str
    display_name: str
    activation_phase: int
    module_dependencies: tuple[str, ...]
    legacy_identifiers: tuple[str, ...] = ()
    enabled_by_default: bool = False


__all__ = ["SectorModule"]
