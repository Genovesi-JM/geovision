"""Report drafting, review, publication, and delivery boundary."""

from app.modules.contracts import DomainModule

definition = DomainModule(
    name="reports",
    purpose="Report versions, QA, publication, documents, and customer delivery.",
    maturity="partial",
)

__all__ = ["definition"]
