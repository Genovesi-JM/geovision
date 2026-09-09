"""Provider-neutral processing-job boundary; implementation belongs to Phase 14."""

from app.modules.contracts import DomainModule

definition = DomainModule(
    name="processing",
    purpose="Asynchronous processing jobs, artifacts, quality, and provider handoff.",
    maturity="foundation",
)

__all__ = ["definition"]
