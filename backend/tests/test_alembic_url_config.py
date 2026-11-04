"""Load the real Alembic environment without a database or application side effects."""
import contextlib
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import context
from alembic.config import Config


class AlembicDatabaseUrlTests(unittest.TestCase):
    def test_url_encoded_credentials_survive_environment_configuration(self):
        env_path = Path(__file__).resolve().parents[1] / "alembic" / "env.py"
        for password in ("plain-safe-password", "encoded%21%40%25password", "%25%28here%29s"):
            with self.subTest(password=password):
                url = "postgresql://synthetic:" + password + "@example.invalid/synthetic"
                config = Config()
                package = types.ModuleType("app")
                package.__path__ = []
                database = types.ModuleType("app.database")
                database.Base = types.SimpleNamespace(metadata=object())
                models = types.ModuleType("app.models")
                settings = types.ModuleType("app.config")
                settings.DATABASE_URL = url
                modules = {"app": package, "app.database": database, "app.models": models, "app.config": settings}
                with patch.dict(sys.modules, modules), \
                     patch.object(context, "config", config, create=True), \
                     patch.object(context, "is_offline_mode", return_value=True), \
                     patch.object(context, "configure") as configure, \
                     patch.object(context, "begin_transaction", return_value=contextlib.nullcontext()), \
                     patch.object(context, "run_migrations"):
                    runpy.run_path(str(env_path))
                self.assertEqual(config.get_main_option("sqlalchemy.url"), url)
                self.assertEqual(configure.call_args.kwargs["url"], url)


if __name__ == "__main__":
    unittest.main()
