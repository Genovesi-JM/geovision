"""Identity domain boundary; provider cutover belongs to Phase 3."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="identity",
    purpose="Authentication identities, sessions, profiles, and principals.",
    maturity="implemented-transitional",
    routes=(
        RouterMount("identity.auth", "identity", "app.routers.auth", 10),
        RouterMount("identity.me", "identity", "app.routers.me", 50),
    ),
)

__all__ = ["definition"]
