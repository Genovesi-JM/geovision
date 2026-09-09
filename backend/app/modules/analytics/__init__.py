"""Validated analytics, KPI, observation, and risk-computation boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="analytics",
    purpose="Validated measurements, KPI definitions, observations, and risk context.",
    maturity="implemented-transitional",
    routes=(
        RouterMount(
            "analytics.ai",
            "analytics",
            "app.routers.ai",
            30,
            prefix="/ai",
            tags=("ai",),
        ),
        RouterMount("analytics.kpi", "analytics", "app.routers.kpi", 60),
        RouterMount("analytics.risk", "analytics", "app.routers.risk", 120),
    ),
)

__all__ = ["definition"]
