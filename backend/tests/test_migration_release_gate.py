from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


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
        pytest.skip(f"{POSTGRES_TEST_URL_ENV} is only supplied by the PostgreSQL CI job")

    base_url = make_url(configured_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.fail(f"{POSTGRES_TEST_URL_ENV} must select a disposable PostgreSQL server")

    suffix = uuid.uuid4().hex[:12]
    names = (
        f"{TEMP_DATABASE_PREFIX}clean_{suffix}",
        f"{TEMP_DATABASE_PREFIX}upgrade_{suffix}",
    )
    assert all(re.fullmatch(r"[a-z0-9_]+", name) for name in names)

    admin_url = base_url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    quoted_names = [admin_engine.dialect.identifier_preparer.quote(name) for name in names]
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
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == expected_head
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
            assert connection.execute(
                text(
                    "SELECT udt_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'assets' "
                    "AND column_name = 'geometry'"
                )
            ).scalar_one() == "geometry"
            assert connection.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                    "AND tablename = 'assets' AND indexname = 'ix_assets_geometry_gist'"
                )
            ).scalar_one().upper().find("USING GIST") >= 0
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
