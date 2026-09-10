from unittest.mock import Mock

import pytest


def test_compatibility_bootstrap_preserves_existing_seed_sequence(monkeypatch):
    from app import startup_bootstrap

    session = Mock()
    calls = []
    monkeypatch.setattr(
        startup_bootstrap.database,
        "ensure_legacy_schema",
        lambda: calls.append("schema"),
    )
    monkeypatch.setattr(startup_bootstrap.database, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        startup_bootstrap,
        "sync_enabled_sector_definitions",
        lambda db: calls.append(("sectors", db)),
    )
    monkeypatch.setattr(
        startup_bootstrap,
        "seed_shop_products",
        lambda db: calls.append(("shop", db)),
    )
    monkeypatch.setattr(
        startup_bootstrap,
        "seed_kit_products",
        lambda db: calls.append(("kits", db)),
    )
    monkeypatch.setattr(
        startup_bootstrap,
        "sync_catalog_from_legacy",
        lambda db: calls.append(("catalog", db)),
    )
    monkeypatch.setattr(startup_bootstrap, "seed_admin_users", lambda: 0)

    startup_bootstrap.run_compatibility_bootstrap()

    assert calls == [
        "schema",
        ("sectors", session),
        ("shop", session),
        ("kits", session),
        ("catalog", session),
    ]
    session.close.assert_called_once_with()


def test_default_bootstrap_keeps_legacy_best_effort_behavior(monkeypatch):
    from app import startup_bootstrap

    session = Mock()
    monkeypatch.setattr(
        startup_bootstrap.database,
        "ensure_legacy_schema",
        Mock(side_effect=RuntimeError("legacy schema drift")),
    )
    monkeypatch.setattr(startup_bootstrap.database, "SessionLocal", lambda: session)
    monkeypatch.setattr(startup_bootstrap, "sync_enabled_sector_definitions", Mock())
    monkeypatch.setattr(startup_bootstrap, "seed_shop_products", Mock())
    monkeypatch.setattr(startup_bootstrap, "seed_kit_products", Mock())
    monkeypatch.setattr(startup_bootstrap, "sync_catalog_from_legacy", Mock())
    monkeypatch.setattr(startup_bootstrap, "seed_admin_users", lambda: 0)

    startup_bootstrap.run_compatibility_bootstrap()

    session.close.assert_called_once_with()


def test_strict_migration_bootstrap_fails_closed_with_sanitized_error(monkeypatch):
    from app import startup_bootstrap

    sentinel = "postgresql://private-user:private-password@database"
    monkeypatch.setattr(
        startup_bootstrap.database,
        "ensure_legacy_schema",
        Mock(side_effect=RuntimeError(sentinel)),
    )
    monkeypatch.setattr(
        startup_bootstrap.database,
        "SessionLocal",
        lambda: pytest.fail("strict mode must stop before seeding"),
    )

    with pytest.raises(startup_bootstrap.StartupBootstrapError) as caught:
        startup_bootstrap.run_compatibility_bootstrap(strict=True)

    assert str(caught.value) == "legacy schema compatibility bootstrap failed"
    assert sentinel not in str(caught.value)


def test_strict_migration_bootstrap_closes_session_on_seed_failure(monkeypatch):
    from app import startup_bootstrap

    session = Mock()
    sentinel = "secret seed provider response"
    monkeypatch.setattr(startup_bootstrap.database, "ensure_legacy_schema", Mock())
    monkeypatch.setattr(startup_bootstrap.database, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        startup_bootstrap,
        "sync_enabled_sector_definitions",
        Mock(side_effect=RuntimeError(sentinel)),
    )

    with pytest.raises(startup_bootstrap.StartupBootstrapError) as caught:
        startup_bootstrap.run_compatibility_bootstrap(strict=True)

    assert str(caught.value) == "reference-data bootstrap failed"
    assert sentinel not in str(caught.value)
    session.close.assert_called_once_with()


def test_start_migration_wrapper_selects_strict_bootstrap(monkeypatch):
    import start
    from app import startup_bootstrap

    calls = []
    monkeypatch.setattr(
        startup_bootstrap,
        "run_compatibility_bootstrap",
        lambda *, strict: calls.append(strict),
    )

    start._run_compatibility_bootstrap()

    assert calls == [True]
