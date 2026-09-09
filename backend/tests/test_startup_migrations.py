import subprocess

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
