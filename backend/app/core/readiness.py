"""Infrastructure readiness checks with secret-free public failure responses."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine


_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def expected_migration_heads(config_path: Path | None = None) -> frozenset[str]:
    """Return the schema heads packaged with this application image."""

    path = config_path or _BACKEND_ROOT / "alembic.ini"
    config = Config(str(path))
    script_location = Path(config.get_main_option("script_location"))
    if not script_location.is_absolute():
        script_location = path.parent / script_location
    config.set_main_option("script_location", str(script_location.resolve()))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def assert_database_ready(
    engine: Engine | None,
    *,
    require_current_schema: bool,
    config_path: Path | None = None,
) -> None:
    """Raise unless the database is reachable and, when required, current."""

    if engine is None:
        raise RuntimeError("database engine is not initialized")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        if not require_current_schema:
            return
        deployed_heads = frozenset(
            str(value)
            for value in connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalars()
        )

    if deployed_heads != expected_migration_heads(config_path):
        raise RuntimeError("database schema is not at the packaged migration head")
