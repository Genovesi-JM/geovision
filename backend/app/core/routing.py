"""Transport-neutral router metadata used by the composition root."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RouterMount:
    """Describe one legacy router mount without importing FastAPI or the router."""

    key: str
    owner: str
    import_path: str
    order: int
    attribute: str = "router"
    prefix: str = ""
    tags: tuple[str, ...] = ()
    secondary_owners: tuple[str, ...] = ()


__all__ = ["RouterMount"]
