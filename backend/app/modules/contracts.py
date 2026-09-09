"""Metadata contracts for explicit modular-monolith domain boundaries."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.routing import RouterMount


@dataclass(frozen=True, slots=True)
class DomainModule:
    """A domain's public identity and currently owned compatibility routes."""

    name: str
    purpose: str
    maturity: str
    dependencies: tuple[str, ...] = ("core",)
    routes: tuple[RouterMount, ...] = ()


__all__ = ["DomainModule", "RouterMount"]
