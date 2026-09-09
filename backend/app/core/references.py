"""Provider-independent references to external systems."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID


_NAMESPACE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")


def _normalize_namespace(value: str, label: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    if not _NAMESPACE.fullmatch(normalized):
        raise ValueError(f"{label} must be a stable lowercase namespace")
    return normalized


@dataclass(frozen=True, slots=True)
class ExternalReference:
    """Bind one opaque provider reference to an authoritative GeoVision UUID.

    Provider values are never parsed or used to generate ``internal_id``. This
    value object can wrap existing dedicated external-ID columns without a
    schema migration; a canonical reference table can be added after workspace
    and generic Asset ownership are stable.
    """

    internal_id: UUID
    provider: str
    resource_type: str
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "internal_id", UUID(str(self.internal_id)))
        object.__setattr__(self, "provider", _normalize_namespace(self.provider, "provider"))
        object.__setattr__(
            self,
            "resource_type",
            _normalize_namespace(self.resource_type, "resource_type"),
        )
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("external reference value must be a non-empty string")
        if any(ord(character) < 32 for character in self.value):
            raise ValueError("external reference value must not contain control characters")

    def as_record(self) -> Mapping[str, Any]:
        """Return a persistence-friendly record without renaming the value to ID."""

        return {
            "internal_id": str(self.internal_id),
            "provider": self.provider,
            "resource_type": self.resource_type,
            "external_reference": self.value,
        }


__all__ = ["ExternalReference"]
