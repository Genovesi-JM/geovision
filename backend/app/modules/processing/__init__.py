"""Provider-neutral processing-job and photogrammetry boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="processing",
    purpose="Asynchronous processing jobs, artifacts, quality, and provider handoff.",
    maturity="implemented",
    dependencies=("core", "organizations", "assets", "missions", "datasets", "operations"),
    routes=(
        RouterMount(
            "processing.jobs",
            "processing",
            "app.routers.processing",
            112,
            secondary_owners=("datasets", "missions", "operations"),
        ),
    ),
)

__all__ = ["definition"]
