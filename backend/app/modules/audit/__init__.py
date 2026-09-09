"""Immutable audit and operational history boundary."""

from app.modules.contracts import DomainModule

definition = DomainModule(
    name="audit",
    purpose="Security audit, domain timelines, provenance, and trace context.",
    maturity="partial",
)

__all__ = ["definition"]
