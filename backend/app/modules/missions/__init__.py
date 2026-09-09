"""Data-acquisition mission boundary; implementation remains in mobile facade."""

from app.modules.contracts import DomainModule

definition = DomainModule(
    name="missions",
    purpose="Acquisition missions, aircraft assignments, approvals, and results.",
    maturity="partial",
)

__all__ = ["definition"]
