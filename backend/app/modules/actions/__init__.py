"""Recommended and assigned action boundary; implementation belongs to Phase 17."""

from app.modules.contracts import DomainModule

definition = DomainModule(
    name="actions",
    purpose="Validated recommendations, commands, assignments, and outcome tracking.",
    maturity="partial",
)

__all__ = ["definition"]
