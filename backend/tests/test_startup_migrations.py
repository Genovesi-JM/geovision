import subprocess
import sys

import pytest


def test_startup_fails_closed_when_alembic_upgrade_fails(monkeypatch):
    import start

    schema_repair_called = False

    def fail_upgrade(*args, **kwargs):
        del args, kwargs
        raise subprocess.CalledProcessError(1, ["alembic", "upgrade", "head"])

    def record_schema_repair():
        nonlocal schema_repair_called
        schema_repair_called = True

    monkeypatch.setattr(start.subprocess, "run", fail_upgrade)
    monkeypatch.setattr(start, "_ensure_schema_columns", record_schema_repair)

    with pytest.raises(SystemExit) as stopped:
        start.main()

    assert stopped.value.code == 1
    assert schema_repair_called is False


def test_migration_job_runs_bounded_upgrade_and_repair_without_server(monkeypatch):
    import start

    invocations = []
    repaired = []
    served = []

    def record_upgrade(command, **kwargs):
        invocations.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(start.subprocess, "run", record_upgrade)
    monkeypatch.setattr(start, "_ensure_schema_columns", lambda: repaired.append(True))
    monkeypatch.setattr(
        start,
        "_run_compatibility_bootstrap",
        lambda: repaired.append("bootstrap"),
    )
    monkeypatch.setattr(start, "_serve", lambda: served.append(True))

    start.main(("migrate",))

    assert invocations == [
        (
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            {
                "check": True,
                "cwd": start._BACKEND_ROOT,
                "timeout": start.settings.migrate_timeout_seconds,
            },
        )
    ]
    assert repaired == [True, "bootstrap"]
    assert served == []


def test_default_serve_preserves_migrate_then_start_behavior(monkeypatch):
    import start

    calls = []
    monkeypatch.setattr(start.settings, "run_migrations_on_startup", True)
    monkeypatch.setattr(start.settings, "startup_compatibility_bootstrap", True)
    monkeypatch.setattr(start, "_run_migrations", lambda: calls.append("migrate"))
    monkeypatch.setattr(start, "_serve", lambda: calls.append("serve"))

    start.main()

    assert calls == ["migrate", "serve"]
    assert start.settings.startup_compatibility_bootstrap is True


@pytest.mark.parametrize(
    "argv,configured_to_run",
    [
        (("serve", "--skip-migrations"), True),
        (("serve",), False),
    ],
)
def test_api_replica_can_delegate_all_startup_schema_writes(
    monkeypatch,
    argv,
    configured_to_run,
):
    import start

    served = []
    monkeypatch.setattr(
        start.settings,
        "run_migrations_on_startup",
        configured_to_run,
    )
    monkeypatch.setattr(start.settings, "startup_compatibility_bootstrap", True)
    monkeypatch.setattr(
        start,
        "_run_migrations",
        lambda: pytest.fail("API replicas must not run migrations"),
    )
    monkeypatch.setattr(start, "_serve", lambda: served.append(True))

    start.main(argv)

    assert served == [True]
    assert start.settings.startup_compatibility_bootstrap is False


def test_application_can_skip_legacy_schema_and_seed_writes(monkeypatch):
    from app import main as app_main

    monkeypatch.setattr(app_main.settings, "startup_compatibility_bootstrap", False)
    monkeypatch.setattr(
        app_main,
        "run_compatibility_bootstrap",
        lambda: pytest.fail("legacy and seed writes must be disabled"),
    )
    monkeypatch.setattr(app_main, "register_application_routes", lambda application: None)

    application = app_main.create_application()

    assert any(route.path == "/health" for route in application.routes)


def test_application_preserves_compatibility_bootstrap_by_default(monkeypatch):
    from app import main as app_main

    calls = []
    monkeypatch.setattr(app_main.settings, "startup_compatibility_bootstrap", True)
    monkeypatch.setattr(
        app_main,
        "run_compatibility_bootstrap",
        lambda: calls.append("bootstrap"),
    )
    monkeypatch.setattr(app_main, "register_application_routes", lambda application: None)

    app_main.create_application()

    assert calls == ["bootstrap"]
