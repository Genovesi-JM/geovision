"""Explicit boundary for configured narrative providers without usable access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class UnavailableNarrativeProvider:
    def __init__(
        self,
        provider_name: str,
        model_name: str | None = None,
        model_version: str = "unavailable-unversioned",
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self.model_version = model_version

    def generate(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        del context
        raise RuntimeError("configured narrative provider is unavailable")


__all__ = ["UnavailableNarrativeProvider"]
