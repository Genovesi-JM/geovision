"""Dataset, file, provenance, and upload lifecycle boundary."""

from app.modules.contracts import DomainModule, RouterMount

definition = DomainModule(
    name="datasets",
    purpose="Captured and imported datasets, files, metadata, and storage lifecycle.",
    maturity="implemented",
    dependencies=("core", "organizations", "assets", "missions"),
    routes=(
        RouterMount("datasets.api", "datasets", "app.routers.datasets", 110),
    ),
)

__all__ = ["definition"]
