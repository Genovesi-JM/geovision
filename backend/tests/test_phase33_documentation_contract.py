from __future__ import annotations

from pathlib import Path
import re

from app.core.event_names import CANONICAL_EVENT_NAMES
from app.modules.organizations.domain import (
    CUSTOMER_ROLE_PERMISSIONS,
    INTERNAL_ROLE_PERMISSIONS,
)
from app.sectors.registry import REQUIRED_SECTOR_NAMES


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def test_phase33_engineering_guide_links_every_required_document():
    guide = (DOCS / "README.md").read_text(encoding="utf-8")
    required = (
        "ENTITY_RELATIONSHIPS.md",
        "EVENT_CATALOG.md",
        "EXTENDING_GEOVISION.md",
        "INTEGRATION_PROVIDER_CATALOG.md",
        "KNOWN_LIMITATIONS.md",
        "ONBOARDING_FLOW.md",
        "PERMISSIONS_MATRIX.md",
        "PHASE_33_READINESS.md",
        "PRODUCTION_LAUNCH.md",
        "RELEASE_CHECKLIST.md",
    )
    for name in required:
        assert (DOCS / name).is_file(), name
        assert name in guide, name

    relative_links = re.findall(r"\[[^]]+\]\(([^)]+)\)", guide)
    for target in relative_links:
        if target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        path = target.split("#", 1)[0]
        assert (DOCS / path).resolve().is_file(), target


def test_event_catalog_contains_the_complete_executable_vocabulary():
    catalog = (DOCS / "EVENT_CATALOG.md").read_text(encoding="utf-8")
    missing = sorted(event for event in CANONICAL_EVENT_NAMES if f"`{event}`" not in catalog)
    assert missing == []


def test_permissions_matrix_tracks_every_role_and_permission():
    matrix = (DOCS / "PERMISSIONS_MATRIX.md").read_text(encoding="utf-8")
    mappings = {**CUSTOMER_ROLE_PERMISSIONS, **INTERNAL_ROLE_PERMISSIONS}
    for role, permissions in mappings.items():
        assert f"`{role.value}`" in matrix
        for permission in permissions:
            assert f"`{permission}`" in matrix


def test_all_sector_names_appear_in_architecture_and_extension_guides():
    text = "\n".join(
        (DOCS / name).read_text(encoding="utf-8").casefold()
        for name in (
            "MODULAR_MONOLITH_ARCHITECTURE.md",
            "EXTENDING_GEOVISION.md",
            "ENTITY_RELATIONSHIPS.md",
        )
    )
    for sector in REQUIRED_SECTOR_NAMES:
        assert sector in text
