from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.readiness import assert_database_ready, expected_migration_heads


def _versioned_engine(tmp_path: Path, versions: tuple[str, ...]):
    engine = create_engine(f"sqlite:///{tmp_path / 'readiness.db'}")
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)")
        )
        for version in versions:
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
                {"version": version},
            )
    return engine


def test_readiness_accepts_reachable_database_when_schema_check_is_disabled(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reachable.db'}")

    assert_database_ready(engine, require_current_schema=False)


def test_readiness_accepts_exact_packaged_migration_heads(tmp_path):
    expected = tuple(expected_migration_heads())
    assert expected
    engine = _versioned_engine(tmp_path, expected)

    assert_database_ready(engine, require_current_schema=True)


def test_readiness_rejects_stale_or_unversioned_schema(tmp_path):
    stale = _versioned_engine(tmp_path, ("stale_revision",))
    with pytest.raises(RuntimeError, match="not at the packaged migration head"):
        assert_database_ready(stale, require_current_schema=True)

    unversioned = create_engine(f"sqlite:///{tmp_path / 'unversioned.db'}")
    with pytest.raises(Exception):
        assert_database_ready(unversioned, require_current_schema=True)


def test_readiness_route_fails_closed_without_leaking_details(monkeypatch):
    from app import main as app_main

    def unavailable(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("postgresql://secret-user:secret-password@private-db")

    monkeypatch.setattr(app_main, "assert_database_ready", unavailable)
    application = app_main.create_application()

    with TestClient(application) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "service unavailable"}
    assert "secret-password" not in response.text
