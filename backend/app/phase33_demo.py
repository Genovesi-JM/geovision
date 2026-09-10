"""Explicit, deterministic, credential-free demo portfolio seed.

This module is deliberately not imported by application startup.  It writes a
clearly labelled synthetic tenant only when called by the dedicated CLI or a
test, and refuses to run in deployed environments.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Any, TypeVar
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Account,
    AccountMember,
    Acquisition,
    Action,
    Asset,
    Company,
    CompanyUser,
    Dataset,
    KpiDefinition,
    KpiValue,
    Observation,
    Report,
    User,
)
from app.modules.analytics.domain import KpiDefinitionSpec, calculate_kpi_status
from app.modules.assets.domain import (
    geometry_bounds,
    geometry_display_center,
    normalize_geometry,
)
from app.modules.datasets.domain import reject_sensitive_metadata
from app.sectors.agriculture.domain import KPI_DEFINITIONS as AGRICULTURE_KPIS
from app.sectors.agriculture.fixtures import demo_fusion_bundle
from app.sectors.environmental.domain import KPI_DEFINITIONS as ENVIRONMENTAL_KPIS
from app.sectors.environmental.fixtures import (
    demo_environmental_bundle,
    resolve_demo_dataset_references as resolve_environmental_references,
)
from app.sectors.infrastructure.domain import KPI_DEFINITIONS as INFRASTRUCTURE_KPIS
from app.sectors.infrastructure.fixtures import (
    demo_infrastructure_bundle,
    resolve_demo_dataset_references as resolve_infrastructure_references,
)
from app.sectors.mining.domain import KPI_DEFINITIONS as MINING_KPIS
from app.sectors.mining.fixtures import (
    demo_mining_bundle,
    resolve_demo_dataset_references as resolve_mining_references,
)
from app.sectors.ports.domain import KPI_DEFINITIONS as PORTS_KPIS
from app.sectors.ports.fixtures import (
    demo_ports_bundle,
    resolve_demo_dataset_references as resolve_ports_references,
)


PHASE33_DEMO_MARKER = "geovision.phase33.synthetic.v1"
PHASE33_DEMO_NOTICE = (
    "SYNTHETIC DEMONSTRATION DATA ONLY — not a real customer, measurement, "
    "finding, recommendation, or report."
)
PHASE33_DEMO_AS_OF = datetime(2026, 9, 10, 8, 0, 0)
_DEMO_NAMESPACE = UUID("d66fac52-8797-5ee0-a201-9ca68dac6f92")
_DEMO_SOURCE = "geovision.phase33.synthetic"


class Phase33DemoSeedError(RuntimeError):
    """Raised before unsafe or conflicting demo seed writes."""


@dataclass(frozen=True)
class Phase33DemoSeedResult:
    organization_id: str
    workspace_id: str
    owner_user_id: str
    member_user_id: str
    attached_user_id: str | None
    access_mode: str
    asset_ids: Mapping[str, str]
    created: Mapping[str, int]

    @property
    def created_total(self) -> int:
        return sum(self.created.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "marker": PHASE33_DEMO_MARKER,
            "synthetic": True,
            "organization_id": self.organization_id,
            "workspace_id": self.workspace_id,
            "owner_user_id": self.owner_user_id,
            "member_user_id": self.member_user_id,
            "attached_user_id": self.attached_user_id,
            "access_mode": self.access_mode,
            "asset_ids": dict(self.asset_ids),
            "created": dict(self.created),
            "created_total": self.created_total,
        }


@dataclass(frozen=True)
class _SectorSeed:
    slug: str
    sector: str
    acquisition_type: str
    definition: KpiDefinitionSpec
    baseline_value: float
    current_value: float
    observation_type: str
    bundle: Callable[[str], dict[str, Any]]
    resolve_references: (
        Callable[[dict[str, Any], dict[str, str]], dict[str, Any]] | None
    ) = None


def phase33_demo_id(*parts: object) -> str:
    """Return the stable UUID used by one Phase 33 demo-owned record."""

    identity = ":".join(str(part).strip().lower() for part in parts)
    if not identity:
        raise ValueError("at least one demo identity component is required")
    return str(uuid5(_DEMO_NAMESPACE, identity))


def _agriculture_bundle(_asset_id: str) -> dict[str, Any]:
    return demo_fusion_bundle(measured_at=PHASE33_DEMO_AS_OF)


def _infrastructure_bundle(_asset_id: str) -> dict[str, Any]:
    return demo_infrastructure_bundle(measured_at=PHASE33_DEMO_AS_OF)


def _environmental_bundle(_asset_id: str) -> dict[str, Any]:
    return demo_environmental_bundle(measured_at=PHASE33_DEMO_AS_OF)


def _mining_bundle(_asset_id: str) -> dict[str, Any]:
    return demo_mining_bundle(measured_at=PHASE33_DEMO_AS_OF)


def _ports_bundle(asset_id: str) -> dict[str, Any]:
    return demo_ports_bundle(asset_id=asset_id, measured_at=PHASE33_DEMO_AS_OF)


_SECTORS = (
    _SectorSeed(
        slug="agriculture",
        sector="AGRICULTURE",
        acquisition_type="DRONE",
        definition=AGRICULTURE_KPIS[0],
        baseline_value=74.0,
        current_value=62.0,
        observation_type="CROP_REVIEW_CANDIDATE",
        bundle=_agriculture_bundle,
    ),
    _SectorSeed(
        slug="infrastructure",
        sector="INFRASTRUCTURE",
        acquisition_type="DRONE",
        definition=INFRASTRUCTURE_KPIS[1],
        baseline_value=0.0,
        current_value=8.0,
        observation_type="PROGRESS_REVIEW_CANDIDATE",
        bundle=_infrastructure_bundle,
        resolve_references=resolve_infrastructure_references,
    ),
    _SectorSeed(
        slug="environmental",
        sector="ENVIRONMENTAL",
        acquisition_type="SATELLITE",
        definition=ENVIRONMENTAL_KPIS[6],
        baseline_value=0.0,
        current_value=3.0,
        observation_type="LAND_COVER_REVIEW_CANDIDATE",
        bundle=_environmental_bundle,
        resolve_references=resolve_environmental_references,
    ),
    _SectorSeed(
        slug="mining",
        sector="MINING",
        acquisition_type="DRONE",
        definition=MINING_KPIS[2],
        baseline_value=10.0,
        current_value=60.0,
        observation_type="STOCKPILE_REVIEW_CANDIDATE",
        bundle=_mining_bundle,
        resolve_references=resolve_mining_references,
    ),
    _SectorSeed(
        slug="ports",
        sector="PORTS_INDUSTRIAL",
        acquisition_type="MANUAL_INSPECTION",
        definition=PORTS_KPIS[1],
        baseline_value=5.0,
        current_value=120.0,
        observation_type="INSPECTION_REVIEW_CANDIDATE",
        bundle=_ports_bundle,
        resolve_references=resolve_ports_references,
    ),
)


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _json(value: Any, *, field_name: str) -> str:
    reject_sensitive_metadata(value, field_name)
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _marked(values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        **dict(values or {}),
        "demo_seed": {
            "marker": PHASE33_DEMO_MARKER,
            "notice": PHASE33_DEMO_NOTICE,
            "synthetic": True,
        },
    }


def _has_marker(value: str | None) -> bool:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return False
    marker = parsed.get("demo_seed") if isinstance(parsed, dict) else None
    return bool(
        isinstance(marker, dict)
        and marker.get("marker") == PHASE33_DEMO_MARKER
        and marker.get("synthetic") is True
    )


T = TypeVar("T")


def _ensure_by_id(
    db: Session,
    *,
    model: type[T],
    row_id: str,
    create: Callable[[], T],
    owned: Callable[[T], bool],
    counter: defaultdict[str, int],
    counter_key: str,
) -> T:
    row = db.get(model, row_id)
    if row is not None:
        if not owned(row):
            raise Phase33DemoSeedError(
                f"Refusing to overwrite non-demo {counter_key} row {row_id}"
            )
        return row
    row = create()
    db.add(row)
    counter[counter_key] += 1
    return row


def _ensure_safe_environment() -> None:
    if settings.is_deployed:
        raise Phase33DemoSeedError(
            "Phase 33 synthetic demo data is restricted to local development/test "
            "and cannot run in staging or production"
        )


def _attached_local_user(db: Session, email: str | None) -> User | None:
    if email is None:
        return None
    canonical_email = str(email).strip().lower()
    if not canonical_email or len(canonical_email) > 320:
        raise Phase33DemoSeedError(
            "Attached user must be selected by one exact canonical email"
        )
    user = db.query(User).filter(User.email == canonical_email).one_or_none()
    if user is None or not user.is_active or not (user.password_hash or "").strip():
        raise Phase33DemoSeedError(
            "Attached user must be one existing active local password account"
        )
    return user


def _ensure_memberships(
    db: Session,
    *,
    organization: Company,
    workspace: Account,
    user: User,
    owner: User,
    role: str,
    display_name: str,
    created_at: datetime,
    counter: defaultdict[str, int],
) -> None:
    organization_member_id = phase33_demo_id(
        "organization-member", organization.id, user.id
    )
    conflicting_organization_member = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization.id,
            CompanyUser.user_id == user.id,
            CompanyUser.id != organization_member_id,
        )
        .one_or_none()
    )
    if conflicting_organization_member is not None:
        raise Phase33DemoSeedError(
            "Attached user already has a non-demo organization membership"
        )
    _ensure_by_id(
        db,
        model=CompanyUser,
        row_id=organization_member_id,
        create=lambda: CompanyUser(
            id=organization_member_id,
            company_id=organization.id,
            user_id=user.id,
            email=user.email,
            name=display_name,
            role=role,
            is_active=True,
            status="active",
            joined_at=created_at,
            created_at=created_at,
            updated_at=created_at,
        ),
        owned=lambda row: row.company_id == organization.id
        and row.user_id == user.id
        and row.email == user.email
        and row.name == display_name
        and row.role == role
        and row.is_active is True
        and row.status == "active",
        counter=counter,
        counter_key="organization_memberships",
    )

    workspace_member = db.get(AccountMember, (workspace.id, user.id))
    if workspace_member is None:
        db.add(
            AccountMember(
                account_id=workspace.id,
                user_id=user.id,
                role=role,
                status="active",
                invited_by_user_id=owner.id,
                invited_at=created_at,
                joined_at=created_at,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        counter["workspace_memberships"] += 1
    elif not (
        workspace_member.account_id == workspace.id
        and workspace_member.user_id == user.id
        and workspace_member.role == role
        and workspace_member.status == "active"
        and workspace_member.invited_by_user_id == owner.id
    ):
        raise Phase33DemoSeedError(
            "Synthetic workspace membership relationship has drifted"
        )


def _ensure_topology(
    db: Session,
    counter: defaultdict[str, int],
    *,
    attach_user_email: str | None,
) -> tuple[Company, Account, User, User, User | None]:
    created_at = PHASE33_DEMO_AS_OF - timedelta(days=90)
    attached_user = _attached_local_user(db, attach_user_email)
    owner_id = phase33_demo_id("user", "owner")
    member_id = phase33_demo_id("user", "member")
    owner_email = "phase33-synthetic-owner@example.invalid"
    member_email = "phase33-synthetic-member@example.invalid"
    for row_id, email in ((owner_id, owner_email), (member_id, member_email)):
        conflict = (
            db.query(User).filter(User.email == email, User.id != row_id).one_or_none()
        )
        if conflict is not None:
            raise Phase33DemoSeedError(
                f"Synthetic demo email is already in use: {email}"
            )

    owner = _ensure_by_id(
        db,
        model=User,
        row_id=owner_id,
        create=lambda: User(
            id=owner_id,
            email=owner_email,
            password_hash=None,
            role="cliente",
            is_active=True,
            created_at=created_at,
            updated_at=created_at,
        ),
        owned=lambda row: row.email == owner_email
        and row.password_hash is None
        and row.role == "cliente"
        and row.is_active is True,
        counter=counter,
        counter_key="users",
    )
    member = _ensure_by_id(
        db,
        model=User,
        row_id=member_id,
        create=lambda: User(
            id=member_id,
            email=member_email,
            password_hash=None,
            role="cliente",
            is_active=True,
            created_at=created_at,
            updated_at=created_at,
        ),
        owned=lambda row: row.email == member_email
        and row.password_hash is None
        and row.role == "cliente"
        and row.is_active is True,
        counter=counter,
        counter_key="users",
    )
    db.flush()

    organization_id = phase33_demo_id("organization")
    organization = _ensure_by_id(
        db,
        model=Company,
        row_id=organization_id,
        create=lambda: Company(
            id=organization_id,
            name="[SYNTHETIC DEMO] GeoVision Five-Sector Portfolio",
            email="phase33-synthetic-organization@example.invalid",
            address=PHASE33_DEMO_NOTICE,
            country="Angola",
            organization_type="demo",
            timezone="Africa/Luanda",
            sectors=_json([item.sector for item in _SECTORS], field_name="sectors"),
            status="active",
            subscription_plan="enterprise",
            max_users=10,
            current_users=3 if attached_user is not None else 2,
            created_at=created_at,
            updated_at=created_at,
        ),
        owned=lambda row: row.name == "[SYNTHETIC DEMO] GeoVision Five-Sector Portfolio"
        and row.email == "phase33-synthetic-organization@example.invalid"
        and row.organization_type == "demo"
        and row.status == "active",
        counter=counter,
        counter_key="organizations",
    )
    db.flush()

    workspace_id = phase33_demo_id("workspace", "five-sector")
    workspace = _ensure_by_id(
        db,
        model=Account,
        row_id=workspace_id,
        create=lambda: Account(
            id=workspace_id,
            organization_id=organization.id,
            name="[SYNTHETIC DEMO] Five-Sector Operations",
            sector_focus=",".join(item.slug for item in _SECTORS),
            entity_type="company",
            customer_type="multi_sector",
            dashboard_profile="operations",
            use_cases=_json(
                ["synthetic_demo_only", PHASE33_DEMO_MARKER],
                field_name="use_cases",
            ),
            org_name=organization.name,
            modules_enabled=_json(
                [
                    "assets",
                    "analytics",
                    "reports",
                    *(item.slug for item in _SECTORS),
                ],
                field_name="modules_enabled",
            ),
            status="active",
            created_at=created_at,
            updated_at=created_at,
        ),
        owned=lambda row: row.organization_id == organization.id
        and row.name == "[SYNTHETIC DEMO] Five-Sector Operations"
        and row.status == "active"
        and PHASE33_DEMO_MARKER in (row.use_cases or ""),
        counter=counter,
        counter_key="workspaces",
    )
    db.flush()

    for user, role in ((owner, "owner"), (member, "member")):
        _ensure_memberships(
            db,
            organization=organization,
            workspace=workspace,
            user=user,
            owner=owner,
            role=role,
            display_name=f"[SYNTHETIC DEMO] {role.title()}",
            created_at=created_at,
            counter=counter,
        )
    if attached_user is not None:
        _ensure_memberships(
            db,
            organization=organization,
            workspace=workspace,
            user=attached_user,
            owner=owner,
            role="member",
            display_name="[SYNTHETIC DEMO] Attached local member",
            created_at=created_at,
            counter=counter,
        )
    db.flush()
    active_member_count = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == organization.id,
            CompanyUser.is_active.is_(True),
            CompanyUser.status == "active",
        )
        .count()
    )
    organization.current_users = active_member_count
    organization.max_users = max(organization.max_users, active_member_count)
    db.flush()
    return organization, workspace, owner, member, attached_user


def _ensure_kpi_definition(
    db: Session,
    *,
    spec: KpiDefinitionSpec,
    counter: defaultdict[str, int],
) -> KpiDefinition:
    expected = {
        "sector": spec.sector,
        "key": spec.key,
        "label": spec.name,
        "name": spec.name,
        "unit": spec.unit,
        "description": spec.description,
        "calculator": spec.calculator,
        "calculator_version": spec.version,
        "importance": spec.importance.value,
        "display_format_json": _json(spec.display_format, field_name="display_format"),
        "status_policy_json": _json(spec.status_policy, field_name="status_policy"),
        "sort_order": spec.sort_order,
        "is_active": True,
    }

    def exact_semantics(row: KpiDefinition) -> bool:
        return all(getattr(row, key) == value for key, value in expected.items())

    existing = (
        db.query(KpiDefinition)
        .filter(
            KpiDefinition.sector == spec.sector,
            KpiDefinition.key == spec.key,
            KpiDefinition.calculator_version == spec.version,
        )
        .order_by(KpiDefinition.created_at, KpiDefinition.id)
        .all()
    )
    if len(existing) > 1 or (existing and not exact_semantics(existing[0])):
        raise Phase33DemoSeedError(
            f"Existing KPI definition conflicts with the {spec.sector}.{spec.key} demo contract"
        )
    if existing:
        return existing[0]
    row_id = phase33_demo_id("kpi-definition", spec.sector, spec.key, spec.version)
    row = _ensure_by_id(
        db,
        model=KpiDefinition,
        row_id=row_id,
        create=lambda: KpiDefinition(
            id=row_id,
            **expected,
            created_at=PHASE33_DEMO_AS_OF - timedelta(days=90),
            updated_at=PHASE33_DEMO_AS_OF - timedelta(days=90),
        ),
        owned=exact_semantics,
        counter=counter,
        counter_key="kpi_definitions",
    )
    db.flush()
    return row


def _period_for(captured_at: datetime, baseline: datetime, current: datetime) -> str:
    baseline_distance = abs((captured_at - baseline).total_seconds())
    current_distance = abs((current - captured_at).total_seconds())
    return "baseline" if baseline_distance <= current_distance else "current"


def _ensure_sector_history(
    db: Session,
    *,
    organization: Company,
    workspace: Account,
    owner: User,
    member: User,
    spec: _SectorSeed,
    counter: defaultdict[str, int],
) -> str:
    asset_id = phase33_demo_id("asset", spec.slug)
    bundle = spec.bundle(asset_id)
    raw_datasets = list(bundle.get("datasets", []))
    if len(raw_datasets) < 2:
        raise Phase33DemoSeedError(f"{spec.slug} demo fixture has no history")
    dataset_ids = {
        str(item["name"]): phase33_demo_id("dataset", spec.slug, item["name"])
        for item in raw_datasets
    }
    if len(dataset_ids) != len(raw_datasets):
        raise Phase33DemoSeedError(f"{spec.slug} demo dataset names are not unique")
    if spec.resolve_references is not None:
        bundle = spec.resolve_references(bundle, dataset_ids)
    asset_values = dict(bundle["asset"])
    geometry = normalize_geometry(asset_values.get("geometry"))
    bounds = geometry_bounds(geometry)
    center = geometry_display_center(geometry)
    asset = _ensure_by_id(
        db,
        model=Asset,
        row_id=asset_id,
        create=lambda: Asset(
            id=asset_id,
            organization_id=organization.id,
            workspace_id=workspace.id,
            sector=spec.sector,
            asset_type=str(asset_values["asset_type"]),
            name=f"[SYNTHETIC DEMO] {asset_values['name']}",
            description=PHASE33_DEMO_NOTICE,
            status="active",
            external_reference=f"{PHASE33_DEMO_MARKER}:{spec.slug}",
            location_label=f"Synthetic location — {asset_values.get('location_label', '')}",
            geometry_geojson=_json(geometry, field_name="geometry"),
            bbox_min_x=bounds[0] if bounds else None,
            bbox_min_y=bounds[1] if bounds else None,
            bbox_max_x=bounds[2] if bounds else None,
            bbox_max_y=bounds[3] if bounds else None,
            centroid_latitude=center[0] if center else None,
            centroid_longitude=center[1] if center else None,
            metadata_json=_json(
                _marked({**dict(asset_values.get("metadata", {})), "synthetic": True}),
                field_name="asset_metadata",
            ),
            legacy_source="phase33_demo",
            legacy_source_id=spec.slug,
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
            created_at=PHASE33_DEMO_AS_OF - timedelta(days=75),
            updated_at=PHASE33_DEMO_AS_OF,
        ),
        owned=lambda row: row.organization_id == organization.id
        and row.workspace_id == workspace.id
        and row.sector == spec.sector
        and _has_marker(row.metadata_json),
        counter=counter,
        counter_key="assets",
    )
    db.flush()

    capture_dates = [
        item.get("capture_date") or PHASE33_DEMO_AS_OF for item in bundle["datasets"]
    ]
    baseline_at, current_at = min(capture_dates), max(capture_dates)
    acquisitions: dict[str, Acquisition] = {}
    for period, captured_at in (("baseline", baseline_at), ("current", current_at)):
        acquisition_id = phase33_demo_id("acquisition", spec.slug, period)
        acquisition_number = f"P33-{spec.slug.upper()}-{period.upper()}"
        conflict = (
            db.query(Acquisition)
            .filter(
                Acquisition.acquisition_number == acquisition_number,
                Acquisition.id != acquisition_id,
            )
            .one_or_none()
        )
        if conflict is not None:
            raise Phase33DemoSeedError(
                f"Synthetic acquisition number is already in use: {acquisition_number}"
            )
        acquisitions[period] = _ensure_by_id(
            db,
            model=Acquisition,
            row_id=acquisition_id,
            create=lambda period=period,
            captured_at=captured_at,
            acquisition_id=acquisition_id,
            acquisition_number=acquisition_number: Acquisition(
                id=acquisition_id,
                acquisition_number=acquisition_number,
                organization_id=organization.id,
                workspace_id=workspace.id,
                asset_id=asset.id,
                acquisition_type=spec.acquisition_type,
                title=f"[SYNTHETIC DEMO] {spec.slug.title()} {period} acquisition",
                description=PHASE33_DEMO_NOTICE,
                state="COMPLETED",
                provider_code="synthetic_fixture",
                provider_reference=f"{PHASE33_DEMO_MARKER}:{spec.slug}:{period}",
                provenance_json=_json(
                    _marked({"period": period, "synthetic": True}),
                    field_name="acquisition_provenance",
                ),
                metadata_json=_json(
                    _marked({"period": period, "synthetic": True}),
                    field_name="acquisition_metadata",
                ),
                output_refs_json="[]",
                started_at=captured_at - timedelta(hours=2),
                captured_at=captured_at,
                completed_at=captured_at + timedelta(hours=1),
                lifecycle_version=1,
                legacy_source="phase33_demo",
                legacy_source_id=f"{spec.slug}:{period}",
                created_by_user_id=owner.id,
                updated_by_user_id=owner.id,
                created_at=captured_at - timedelta(hours=2),
                updated_at=captured_at + timedelta(hours=1),
            ),
            owned=lambda row: row.organization_id == organization.id
            and row.workspace_id == workspace.id
            and row.asset_id == asset.id
            and row.provider_reference
            == f"{PHASE33_DEMO_MARKER}:{spec.slug}:{period}"
            and _has_marker(row.provenance_json),
            counter=counter,
            counter_key="acquisitions",
        )
    db.flush()

    period_datasets: dict[str, list[Dataset]] = {"baseline": [], "current": []}
    for index, item in enumerate(bundle["datasets"]):
        captured_at = item.get("capture_date") or PHASE33_DEMO_AS_OF
        period = _period_for(captured_at, baseline_at, current_at)
        acquisition = acquisitions[period]
        dataset_id = dataset_ids[str(item["name"])]
        dataset = _ensure_by_id(
            db,
            model=Dataset,
            row_id=dataset_id,
            create=lambda item=item,
            captured_at=captured_at,
            acquisition=acquisition,
            dataset_id=dataset_id,
            index=index: Dataset(
                id=dataset_id,
                company_id=organization.id,
                workspace_id=workspace.id,
                asset_id=asset.id,
                mission_id=acquisition.id,
                name=f"[SYNTHETIC DEMO] {item['name']}",
                description=PHASE33_DEMO_NOTICE,
                source_tool="phase33_demo_seed",
                data_type="synthetic_evidence",
                source=_DEMO_SOURCE,
                dataset_type=str(item.get("dataset_type") or "OTHER"),
                provider_code="synthetic_fixture",
                source_reference=f"{PHASE33_DEMO_MARKER}:{spec.slug}:{index}",
                storage_provider="local",
                crs=item.get("crs") or "EPSG:4326",
                resolution=item.get("resolution"),
                resolution_unit=item.get("resolution_unit"),
                processing_level=str(item.get("processing_level") or "DERIVED"),
                quality_status=str(item.get("quality_status") or "PASSED"),
                provenance_json=_json(
                    _marked({**dict(item.get("provenance", {})), "synthetic": True}),
                    field_name="dataset_provenance",
                ),
                status="ready",
                sector=spec.sector,
                capture_date=captured_at,
                metadata_json=_json(
                    _marked({**dict(item.get("metadata", {})), "synthetic": True}),
                    field_name="dataset_metadata",
                ),
                file_count=0,
                total_size_bytes=0,
                created_at=captured_at,
                updated_at=captured_at,
                processed_at=captured_at + timedelta(hours=1),
                created_by_user_id=owner.id,
                lifecycle_version=1,
            ),
            owned=lambda row: row.company_id == organization.id
            and row.workspace_id == workspace.id
            and row.asset_id == asset.id
            and row.mission_id == acquisition.id
            and row.source == _DEMO_SOURCE
            and _has_marker(row.provenance_json),
            counter=counter,
            counter_key="datasets",
        )
        period_datasets[period].append(dataset)
    for period, rows in period_datasets.items():
        acquisitions[period].output_refs_json = _json(
            [row.id for row in rows], field_name="acquisition_output_refs"
        )
    db.flush()

    definition = _ensure_kpi_definition(db, spec=spec.definition, counter=counter)
    if not spec.definition.status_policy:
        raise Phase33DemoSeedError(
            f"{spec.slug} demo KPI requires an explicit status policy"
        )
    observations: dict[str, Observation] = {}
    actions: dict[str, Action] = {}
    kpis: dict[str, KpiValue] = {}
    for period, measured_at, value in (
        ("baseline", baseline_at, spec.baseline_value),
        ("current", current_at, spec.current_value),
    ):
        status = calculate_kpi_status(
            value,
            spec.definition.status_policy,
            confidence=0.9,
        ).value
        acquisition = acquisitions[period]
        dataset = min(
            period_datasets[period],
            key=lambda row: abs(
                ((row.capture_date or measured_at) - measured_at).total_seconds()
            ),
        )
        kpi_id = phase33_demo_id("kpi-value", spec.slug, period)
        kpis[period] = _ensure_by_id(
            db,
            model=KpiValue,
            row_id=kpi_id,
            create=lambda period=period,
            measured_at=measured_at,
            value=value,
            status=status,
            kpi_id=kpi_id,
            acquisition=acquisition,
            dataset=dataset: KpiValue(
                id=kpi_id,
                kpi_definition_id=definition.id,
                account_id=workspace.id,
                organization_id=organization.id,
                workspace_id=workspace.id,
                asset_id=asset.id,
                dataset_id=dataset.id,
                mission_id=acquisition.id,
                value=str(value),
                numeric_value=value,
                status=status,
                confidence=0.9,
                measured_at=measured_at,
                source=_DEMO_SOURCE,
                algorithm_version=spec.definition.version,
                provenance_json=_json(
                    _marked(
                        {
                            "period": period,
                            "dataset_id": dataset.id,
                            "mission_id": acquisition.id,
                            "synthetic": True,
                        }
                    ),
                    field_name="kpi_provenance",
                ),
                is_baseline=period == "baseline",
                recorded_at=measured_at,
                created_at=measured_at,
            ),
            owned=lambda row: row.organization_id == organization.id
            and row.account_id == workspace.id
            and row.workspace_id == workspace.id
            and row.asset_id == asset.id
            and row.kpi_definition_id == definition.id
            and row.dataset_id == dataset.id
            and row.mission_id == acquisition.id
            and _has_marker(row.provenance_json),
            counter=counter,
            counter_key="kpi_values",
        )

        observation_id = phase33_demo_id("observation", spec.slug, period)
        observations[period] = _ensure_by_id(
            db,
            model=Observation,
            row_id=observation_id,
            create=lambda period=period,
            measured_at=measured_at,
            observation_id=observation_id,
            acquisition=acquisition,
            dataset=dataset: Observation(
                id=observation_id,
                organization_id=organization.id,
                workspace_id=workspace.id,
                asset_id=asset.id,
                mission_id=acquisition.id,
                dataset_id=dataset.id,
                observation_type=spec.observation_type,
                severity="WATCH" if period == "baseline" else "WARNING",
                geometry_geojson=asset.geometry_geojson,
                value_json=_json(
                    _marked(
                        {
                            "period": period,
                            "summary": "Synthetic candidate for interface demonstration",
                        }
                    ),
                    field_name="observation_value",
                ),
                metadata_json=_json(
                    _marked({"synthetic": True, "period": period}),
                    field_name="observation_metadata",
                ),
                confidence=0.82,
                source=_DEMO_SOURCE,
                algorithm_key=f"geovision.phase33.synthetic.{spec.slug}",
                algorithm_version="1.0.0",
                provenance_json=_json(
                    _marked(
                        {
                            "dataset_id": dataset.id,
                            "mission_id": acquisition.id,
                            "synthetic": True,
                        }
                    ),
                    field_name="observation_provenance",
                ),
                validation_status="VALIDATED",
                validated_by_user_id=member.id,
                validated_at=measured_at + timedelta(hours=2),
                detected_at=measured_at,
                created_at=measured_at,
                updated_at=measured_at + timedelta(hours=2),
            ),
            owned=lambda row: row.organization_id == organization.id
            and row.workspace_id == workspace.id
            and row.asset_id == asset.id
            and row.mission_id == acquisition.id
            and row.dataset_id == dataset.id
            and _has_marker(row.provenance_json),
            counter=counter,
            counter_key="observations",
        )
        db.flush()

        action_id = phase33_demo_id("action", spec.slug, period)
        deduplication_key = f"{PHASE33_DEMO_MARKER}:{spec.slug}:{period}"
        conflict = (
            db.query(Action)
            .filter(
                Action.organization_id == organization.id,
                Action.deduplication_key == deduplication_key,
                Action.id != action_id,
            )
            .one_or_none()
        )
        if conflict is not None:
            raise Phase33DemoSeedError(
                f"Synthetic action marker is already in use: {deduplication_key}"
            )
        is_baseline = period == "baseline"
        actions[period] = _ensure_by_id(
            db,
            model=Action,
            row_id=action_id,
            create=lambda period=period,
            measured_at=measured_at,
            action_id=action_id,
            observation_id=observation_id,
            deduplication_key=deduplication_key,
            is_baseline=is_baseline: Action(
                id=action_id,
                organization_id=organization.id,
                workspace_id=workspace.id,
                asset_id=asset.id,
                source_observation_id=observation_id,
                source_rule_key=f"phase33.synthetic.{spec.slug}.{period}",
                source_rule_version="1.0.0",
                priority="MEDIUM" if is_baseline else "HIGH",
                title=f"[SYNTHETIC DEMO] Review {spec.slug} {period} candidate",
                description=PHASE33_DEMO_NOTICE,
                status="COMPLETED" if is_baseline else "OPEN",
                due_date=measured_at + timedelta(days=7),
                assigned_to_user_id=member.id,
                recommendation_refs_json=_json(
                    [_marked({"kind": "synthetic_demo"})],
                    field_name="recommendation_refs",
                ),
                outcome_json=_json(
                    _marked(
                        {
                            "result": (
                                "simulated_follow_up_complete"
                                if is_baseline
                                else "pending_synthetic_review"
                            )
                        }
                    ),
                    field_name="action_outcome",
                ),
                deduplication_key=deduplication_key,
                lifecycle_version=2 if is_baseline else 1,
                created_by_user_id=owner.id,
                completed_by_user_id=member.id if is_baseline else None,
                completed_at=measured_at + timedelta(days=2) if is_baseline else None,
                created_at=measured_at + timedelta(hours=3),
                updated_at=(
                    measured_at + timedelta(days=2)
                    if is_baseline
                    else measured_at + timedelta(hours=3)
                ),
            ),
            owned=lambda row: row.organization_id == organization.id
            and row.workspace_id == workspace.id
            and row.asset_id == asset.id
            and row.source_observation_id == observation_id
            and row.assigned_to_user_id == member.id
            and _has_marker(row.outcome_json),
            counter=counter,
            counter_key="actions",
        )
    db.flush()

    previous_report_id: str | None = None
    for revision, period in enumerate(("baseline", "current"), start=1):
        acquisition = acquisitions[period]
        measured_at = baseline_at if period == "baseline" else current_at
        evidence_ids = [
            *(f"dataset:{row.id}" for row in period_datasets[period]),
            f"kpi:{kpis[period].id}",
            f"observation:{observations[period].id}",
            f"action:{actions[period].id}",
        ]
        context = _marked(
            {
                "schema_version": "geovision.report-context.v1",
                "as_of": measured_at,
                "organization_id": organization.id,
                "workspace_id": workspace.id,
                "asset": {
                    "id": asset.id,
                    "name": asset.name,
                    "sector": asset.sector,
                    "asset_type": asset.asset_type,
                },
                "acquisition_id": acquisition.id,
                "evidence_ids": evidence_ids,
                "limitations": [PHASE33_DEMO_NOTICE],
            }
        )
        context_json = _json(context, field_name="report_context")
        narrative = _marked(
            {
                "schema_version": "geovision.report-narrative.v1",
                "executive_summary": PHASE33_DEMO_NOTICE,
                "sections": [
                    {
                        "heading": "Synthetic demonstration",
                        "paragraphs": [
                            "This deterministic record demonstrates report history and relationships."
                        ],
                    }
                ],
                "evidence_ids": evidence_ids,
                "limitations": [PHASE33_DEMO_NOTICE],
            }
        )
        context_sha256 = hashlib.sha256(context_json.encode()).hexdigest()
        provenance = _marked(
            {
                "schema_version": "geovision.report-provenance.v1",
                "organization_id": organization.id,
                "workspace_id": workspace.id,
                "asset_id": asset.id,
                "acquisition_id": acquisition.id,
                "context_schema_version": "geovision.report-context.v1",
                "context_sha256": context_sha256,
                "template_version": "phase33-demo-v1",
                "narrative_provider": "deterministic_demo",
                "narrative_model": None,
                "narrative_model_version": "geovision-phase33-demo-v1",
                "narrative_schema_version": "geovision.report-narrative.v1",
                "sources": [
                    *(
                        {
                            "kind": "dataset",
                            "id": row.id,
                            "provider": "synthetic_fixture",
                            "version": "phase33-demo-v1",
                        }
                        for row in period_datasets[period]
                    ),
                    {
                        "kind": "kpi",
                        "id": kpis[period].id,
                        "provider": _DEMO_SOURCE,
                        "version": spec.definition.version,
                    },
                    {
                        "kind": "observation",
                        "id": observations[period].id,
                        "provider": _DEMO_SOURCE,
                        "version": "1.0.0",
                    },
                    {
                        "kind": "action",
                        "id": actions[period].id,
                        "provider": "geovision-rules",
                        "version": "1.0.0",
                    },
                ],
                "complete": True,
                "issues": [],
                "synthetic": True,
                "evidence_ids": evidence_ids,
                "limitation": "No downloadable artifact is created by the seed.",
            }
        )
        is_current = period == "current"
        approved_at = measured_at + timedelta(days=2, hours=1) if is_current else None
        published_at = measured_at + timedelta(days=2, hours=2) if is_current else None
        report_status = "PUBLISHED" if is_current else "DRAFT"
        report_id = phase33_demo_id("report", spec.slug, revision)
        generation_key = hashlib.sha256(
            f"{PHASE33_DEMO_MARKER}:{spec.slug}:{revision}".encode()
        ).hexdigest()
        conflict = (
            db.query(Report)
            .filter(Report.generation_key == generation_key, Report.id != report_id)
            .one_or_none()
        )
        if conflict is not None:
            raise Phase33DemoSeedError(
                f"Synthetic report generation key is already in use for {spec.slug}"
            )
        report = _ensure_by_id(
            db,
            model=Report,
            row_id=report_id,
            create=lambda revision=revision,
            period=period,
            measured_at=measured_at,
            report_id=report_id,
            generation_key=generation_key,
            context_json=context_json,
            narrative=narrative,
            provenance=provenance,
            evidence_ids=evidence_ids,
            previous_report_id=previous_report_id,
            acquisition=acquisition,
            context_sha256=context_sha256,
            approved_at=approved_at,
            published_at=published_at,
            report_status=report_status,
            is_current=is_current: Report(
                id=report_id,
                organization_id=organization.id,
                workspace_id=workspace.id,
                asset_id=asset.id,
                acquisition_id=acquisition.id,
                report_type=f"{spec.sector}_INTELLIGENCE",
                title=f"[SYNTHETIC DEMO] {spec.slug.title()} history — revision {revision}",
                template_version="phase33-demo-v1",
                revision=revision,
                status=report_status,
                qa_level="HUMAN_REVIEW",
                context_schema_version="geovision.report-context.v1",
                context_json=context_json,
                context_sha256=context_sha256,
                narrative_provider="deterministic_demo",
                narrative_model=None,
                narrative_model_version="geovision-phase33-demo-v1",
                narrative_schema_version="geovision.report-narrative.v1",
                narrative_json=_json(narrative, field_name="report_narrative"),
                provenance_json=_json(provenance, field_name="report_provenance"),
                qa_result_json=_json(
                    _marked(
                        {
                            "level": "HUMAN_REVIEW",
                            "synthetic": True,
                            "reasons": ["synthetic_demo_record"],
                        }
                    ),
                    field_name="report_qa",
                ),
                supersedes_report_id=previous_report_id,
                generation_key=generation_key,
                generated_at=measured_at + timedelta(days=2),
                approved_at=approved_at,
                published_at=published_at,
                approved_by_user_id=member.id if is_current else None,
                published_by_user_id=owner.id if is_current else None,
                created_by_user_id=owner.id,
                lifecycle_version=4 if is_current else 1,
                created_at=measured_at + timedelta(days=2),
                updated_at=published_at or measured_at + timedelta(days=2),
            ),
            owned=lambda row: row.organization_id == organization.id
            and row.workspace_id == workspace.id
            and row.asset_id == asset.id
            and row.acquisition_id == acquisition.id
            and row.supersedes_report_id == previous_report_id
            and row.generation_key == generation_key
            and row.status == report_status
            and _has_marker(row.provenance_json),
            counter=counter,
            counter_key="reports",
        )
        previous_report_id = report.id
        db.flush()
    return asset.id


def seed_phase33_demo(
    db: Session,
    *,
    attach_user_email: str | None = None,
) -> Phase33DemoSeedResult:
    """Stage the complete Phase 33 demo portfolio in the caller's transaction.

    The caller owns commit/rollback. Re-running this function returns the same
    topology and histories without inserting duplicate demo-owned records. With
    no ``attach_user_email`` the generated identities are intentionally
    passwordless and the result is database-only. Supplying an email attaches
    one existing active local password account without changing its credentials.
    """

    _ensure_safe_environment()
    counter: defaultdict[str, int] = defaultdict(int)
    organization, workspace, owner, member, attached_user = _ensure_topology(
        db,
        counter,
        attach_user_email=attach_user_email,
    )
    asset_ids = {
        spec.slug: _ensure_sector_history(
            db,
            organization=organization,
            workspace=workspace,
            owner=owner,
            member=member,
            spec=spec,
            counter=counter,
        )
        for spec in _SECTORS
    }
    db.flush()
    return Phase33DemoSeedResult(
        organization_id=organization.id,
        workspace_id=workspace.id,
        owner_user_id=owner.id,
        member_user_id=member.id,
        attached_user_id=attached_user.id if attached_user is not None else None,
        access_mode=(
            "attached_local_user" if attached_user is not None else "database_only"
        ),
        asset_ids=asset_ids,
        created=dict(sorted(counter.items())),
    )


__all__ = [
    "PHASE33_DEMO_AS_OF",
    "PHASE33_DEMO_MARKER",
    "PHASE33_DEMO_NOTICE",
    "Phase33DemoSeedError",
    "Phase33DemoSeedResult",
    "phase33_demo_id",
    "seed_phase33_demo",
]
