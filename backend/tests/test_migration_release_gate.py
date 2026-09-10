from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Barrier, Event, Lock
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import sessionmaker


BACKEND_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_TEST_URL_ENV = "GEOVISION_MIGRATION_TEST_DATABASE_URL"
TEMP_DATABASE_PREFIX = "geovision_release_gate_"


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))


def test_migration_graph_has_one_head_and_resolvable_parents() -> None:
    scripts = _script_directory()
    heads = scripts.get_heads()
    assert len(heads) == 1

    revisions = tuple(scripts.walk_revisions(base="base", head="heads"))
    assert revisions
    revision_ids = {revision.revision for revision in revisions}
    for revision in revisions:
        parents = revision.down_revision
        if parents is None:
            continue
        if isinstance(parents, str):
            parents = (parents,)
        assert set(parents) <= revision_ids


def _database_url(base_url: URL, database_name: str) -> str:
    return base_url.set(database=database_name).render_as_string(hide_password=False)


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": database_url,
            "ENV": "test",
            "STARTUP_COMPATIBILITY_BOOTSTRAP": "false",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.fixture(scope="module")
def postgres_databases() -> tuple[str, str]:
    configured_url = os.getenv(POSTGRES_TEST_URL_ENV)
    if not configured_url:
        pytest.skip(
            f"{POSTGRES_TEST_URL_ENV} is only supplied by the PostgreSQL CI job"
        )

    base_url = make_url(configured_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.fail(
            f"{POSTGRES_TEST_URL_ENV} must select a disposable PostgreSQL server"
        )

    suffix = uuid.uuid4().hex[:12]
    names = (
        f"{TEMP_DATABASE_PREFIX}clean_{suffix}",
        f"{TEMP_DATABASE_PREFIX}upgrade_{suffix}",
    )
    assert all(re.fullmatch(r"[a-z0-9_]+", name) for name in names)

    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    quoted_names = [
        admin_engine.dialect.identifier_preparer.quote(name) for name in names
    ]
    try:
        with admin_engine.connect() as connection:
            for quoted_name in quoted_names:
                connection.execute(text(f"CREATE DATABASE {quoted_name}"))
        yield tuple(_database_url(base_url, name) for name in names)
    finally:
        with admin_engine.connect() as connection:
            for name, quoted_name in zip(names, quoted_names, strict=True):
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                    ),
                    {"database_name": name},
                )
                connection.execute(text(f"DROP DATABASE IF EXISTS {quoted_name}"))
        admin_engine.dispose()


def _assert_current_head(database_url: str) -> None:
    _run_alembic(database_url, "current", "--check-heads")
    expected_head = _script_directory().get_current_head()
    assert expected_head is not None
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                == expected_head
            )
    finally:
        engine.dispose()


def test_clean_postgres_postgis_database_upgrades_to_head(
    postgres_databases: tuple[str, str],
) -> None:
    clean_url, _ = postgres_databases
    _run_alembic(clean_url, "upgrade", "head")
    _assert_current_head(clean_url)

    engine = create_engine(clean_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
            ).scalar_one()
            assert (
                connection.execute(
                    text(
                        "SELECT udt_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = 'assets' "
                        "AND column_name = 'geometry'"
                    )
                ).scalar_one()
                == "geometry"
            )
            assert (
                connection.execute(
                    text(
                        "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                        "AND tablename = 'assets' AND indexname = 'ix_assets_geometry_gist'"
                    )
                )
                .scalar_one()
                .upper()
                .find("USING GIST")
                >= 0
            )
    finally:
        engine.dispose()


def test_representative_previous_postgres_schema_preserves_rows_at_head(
    postgres_databases: tuple[str, str],
) -> None:
    _, upgrade_url = postgres_databases
    _run_alembic(upgrade_url, "upgrade", "odoo_erp_v1")

    engine = create_engine(upgrade_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO audit_log "
                    "(id, user_id, user_email, action, resource_type, resource_id, "
                    "details, ip_address, user_agent, created_at) VALUES "
                    "(:id, NULL, NULL, :action, :resource_type, :resource_id, "
                    ":details, NULL, NULL, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": "release-gate-audit",
                    "action": "release_gate.previous_schema",
                    "resource_type": "release_gate",
                    "resource_id": "representative-row",
                    "details": '{"preserve":true}',
                },
            )
    finally:
        engine.dispose()

    _run_alembic(upgrade_url, "upgrade", "head")
    _assert_current_head(upgrade_url)

    engine = create_engine(upgrade_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT details, outcome FROM audit_log "
                    "WHERE id = 'release-gate-audit'"
                )
            ).one() == ('{"preserve":true}', "UNKNOWN")
    finally:
        engine.dispose()


def test_postgres_service_request_idempotency_recovers_a_real_insert_race(
    postgres_databases: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two transactions crossing the first lookup converge on one request."""

    from app.models import Account, AccountEvent, Asset, Company, Site, User
    from app.modules.identity.domain import AuthorizationContext
    from app.modules.operations import mobile_services

    database_url, _ = postgres_databases
    _run_alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, autoflush=False)
    suffix = uuid.uuid4().hex
    organization_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    site_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
    try:
        with sessions.begin() as db:
            db.add_all(
                [
                    User(
                        id=user_id,
                        email=f"service-race-{suffix}@example.test",
                        role="cliente",
                        is_active=True,
                    ),
                    Company(
                        id=organization_id,
                        name=f"Service race {suffix[:8]}",
                        email=f"service-race-org-{suffix}@example.test",
                        country="Angola",
                        status="active",
                    ),
                    Account(
                        id=workspace_id,
                        organization_id=organization_id,
                        name="Service race workspace",
                        sector_focus="agriculture",
                        entity_type="company",
                        customer_type="business",
                        dashboard_profile="business",
                        use_cases="[]",
                        modules_enabled="[]",
                        status="active",
                    ),
                    Site(
                        id=site_id,
                        company_id=organization_id,
                        name="Service race site",
                        country="Angola",
                        sector="agriculture",
                    ),
                    Asset(
                        id=asset_id,
                        organization_id=organization_id,
                        workspace_id=workspace_id,
                        sector="AGRICULTURE",
                        asset_type="SITE",
                        name="Service race site",
                        status="active",
                        metadata_json="{}",
                        legacy_source="site",
                        legacy_source_id=site_id,
                    ),
                ]
            )

        context = AuthorizationContext(
            user_id=user_id,
            identity_subject=f"internal:{user_id}",
            active_workspace_id=workspace_id,
            active_organization_id=organization_id,
            workspace_role="owner",
            organization_role="owner",
            permissions=frozenset({"workspace:contribute"}),
        )
        first_lookup_barrier = Barrier(2)
        lookup_lock = Lock()
        initial_lookups = 0
        real_lookup = mobile_services._idempotent_service_request

        def synchronized_lookup(*args, **kwargs):
            nonlocal initial_lookups
            result = real_lookup(*args, **kwargs)
            with lookup_lock:
                is_initial = initial_lookups < 2
                if is_initial:
                    initial_lookups += 1
            if is_initial:
                assert result is None
                first_lookup_barrier.wait(timeout=15)
            return result

        monkeypatch.setattr(
            mobile_services,
            "_idempotent_service_request",
            synchronized_lookup,
        )
        idempotency_key = f"postgres-service-race-{suffix}"

        def create_request() -> tuple[str, bool]:
            with sessions() as db:
                actor = db.get(User, user_id)
                assert actor is not None
                item, replayed = mobile_services.create_mobile_service_request(
                    db,
                    actor=actor,
                    context=context,
                    site_id=site_id,
                    request_type="drone_inspection",
                    urgency="high",
                    description="One logical request from two live transactions.",
                    attachments=["customer-upload:race-proof"],
                    idempotency_key=idempotency_key,
                )
                db.commit()
                return item.id, replayed

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = tuple(pool.map(lambda _: create_request(), range(2)))

        assert len({item_id for item_id, _ in results}) == 1
        assert sorted(replayed for _, replayed in results) == [False, True]
        winning_id = results[0][0]
        with sessions() as db:
            assert (
                db.query(mobile_services.MobileServiceRequest)
                .filter(
                    mobile_services.MobileServiceRequest.organization_id
                    == organization_id,
                    mobile_services.MobileServiceRequest.workspace_id == workspace_id,
                    mobile_services.MobileServiceRequest.user_id == user_id,
                    mobile_services.MobileServiceRequest.idempotency_key
                    == idempotency_key,
                )
                .count()
                == 1
            )
            assert (
                db.query(AccountEvent)
                .filter(
                    AccountEvent.company_id == organization_id,
                    AccountEvent.workspace_id == workspace_id,
                    AccountEvent.event_type == "service_request.created",
                    AccountEvent.resource_id == winning_id,
                )
                .count()
                == 1
            )
    finally:
        engine.dispose()


def test_postgres_iot_projection_repairs_serialize_per_device(
    postgres_databases: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two failed receipts cannot split one device/channel KPI definition."""

    from app.core.event_names import EventNames
    from app.core.events import DomainEvent
    from app.iot import intelligence
    from app.models import (
        Account,
        Asset,
        Company,
        IotDevice,
        KpiDefinition,
        KpiValue,
        SensorChannel,
        Site,
        TelemetryReading,
        TelemetryReceipt,
    )
    from app.services.event_consumers import _consume_iot_projection_repair

    database_url, _ = postgres_databases
    _run_alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    sessions = sessionmaker(bind=engine, autoflush=False)
    suffix = uuid.uuid4().hex
    organization_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    site_id = str(uuid.uuid4())
    asset_id = str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    measured_at = datetime.now(timezone.utc).replace(tzinfo=None)
    receipt_ids = (str(uuid.uuid4()), str(uuid.uuid4()))
    try:
        with sessions.begin() as db:
            db.add(
                Company(
                    id=organization_id,
                    name=f"IoT repair race {suffix[:8]}",
                    email=f"iot-repair-org-{suffix}@example.test",
                    country="Angola",
                    status="active",
                )
            )
            db.flush()
            db.add_all(
                [
                    Account(
                        id=workspace_id,
                        organization_id=organization_id,
                        name="IoT repair workspace",
                        sector_focus="agriculture",
                        entity_type="company",
                        customer_type="business",
                        dashboard_profile="business",
                        use_cases="[]",
                        modules_enabled="[]",
                        status="active",
                    ),
                    Site(
                        id=site_id,
                        company_id=organization_id,
                        name="IoT repair site",
                        country="Angola",
                        sector="agriculture",
                    ),
                ]
            )
            db.flush()
            db.add(
                Asset(
                    id=asset_id,
                    organization_id=organization_id,
                    workspace_id=workspace_id,
                    sector="AGRICULTURE",
                    asset_type="SITE",
                    name="IoT repair asset",
                    status="active",
                    metadata_json="{}",
                )
            )
            db.flush()
            db.add(
                IotDevice(
                    id=device_id,
                    public_id=f"iot-repair-{suffix}",
                    company_id=organization_id,
                    site_id=site_id,
                    core_asset_id=asset_id,
                    name="IoT repair sensor",
                    token_hash="test-token-hash",
                    secret_encrypted="test-encrypted-secret",
                )
            )
            db.flush()
            db.add(
                SensorChannel(
                    id=str(uuid.uuid4()),
                    device_id=device_id,
                    key="soil_moisture",
                    label="Soil moisture",
                    measurement_type="soil_moisture",
                    unit="%",
                )
            )
            db.flush()
            for index, receipt_id in enumerate(receipt_ids, start=1):
                message_id = f"iot-repair-race-{suffix}-{index}"
                db.add(
                    TelemetryReceipt(
                        id=receipt_id,
                        device_id=device_id,
                        company_id=organization_id,
                        site_id=site_id,
                        core_asset_id=asset_id,
                        message_id=message_id,
                        provider_code="geovision",
                        protocol_version="geovision.telemetry.v1",
                        stream_id=f"repair-{suffix}",
                        sequence=index,
                        recorded_at=measured_at,
                        measurement_count=1,
                    )
                )
                db.flush()
                db.add(
                    TelemetryReading(
                        id=str(uuid.uuid4()),
                        receipt_id=receipt_id,
                        device_id=device_id,
                        company_id=organization_id,
                        site_id=site_id,
                        core_asset_id=asset_id,
                        message_id=message_id,
                        sequence=index,
                        protocol_version="geovision.telemetry.v1",
                        source="repair-test",
                        channel="soil_moisture",
                        numeric_value=float(20 + index),
                        unit="%",
                        quality="good",
                        recorded_at=measured_at,
                    )
                )

        original_projection = intelligence.materialize_iot_intelligence
        first_inside = Event()
        second_inside = Event()
        release_first = Event()
        state_lock = Lock()
        projection_calls = 0
        in_flight = 0
        max_in_flight = 0

        def controlled_projection(*args, **kwargs):
            nonlocal projection_calls, in_flight, max_in_flight
            with state_lock:
                projection_calls += 1
                ordinal = projection_calls
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            try:
                if ordinal == 1:
                    first_inside.set()
                    assert release_first.wait(timeout=15)
                else:
                    second_inside.set()
                return original_projection(*args, **kwargs)
            finally:
                with state_lock:
                    in_flight -= 1

        monkeypatch.setattr(
            intelligence,
            "materialize_iot_intelligence",
            controlled_projection,
        )

        def repair(receipt_id: str) -> None:
            with sessions() as db:
                event = DomainEvent(
                    name=EventNames.DEVICE_TELEMETRY_RECEIVED,
                    aggregate_type="iot_device",
                    aggregate_id=device_id,
                    payload={
                        "intelligence_reason": "projection_failed",
                        "receipt_id": receipt_id,
                        "device_id": device_id,
                        "organization_id": organization_id,
                        "asset_id": asset_id,
                        "workspace_id": workspace_id,
                    },
                )
                _consume_iot_projection_repair(db, event)
                db.commit()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(repair, receipt_ids[0])
            assert first_inside.wait(timeout=15)
            second = pool.submit(repair, receipt_ids[1])
            try:
                second_was_serialized = not second_inside.wait(timeout=0.75)
            finally:
                release_first.set()
            first.result(timeout=15)
            second.result(timeout=15)

        assert second_was_serialized
        assert max_in_flight == 1
        with sessions() as db:
            assert (
                db.query(KpiDefinition)
                .filter(
                    KpiDefinition.sector == "AGRICULTURE",
                    KpiDefinition.calculator == "iot.telemetry_projection",
                )
                .count()
                == 1
            )
            assert (
                db.query(KpiValue)
                .filter(
                    KpiValue.organization_id == organization_id,
                    KpiValue.workspace_id == workspace_id,
                    KpiValue.asset_id == asset_id,
                )
                .count()
                == 2
            )
    finally:
        engine.dispose()
