"""Migration URL regression tests: synthetic URLs, real Config, no database.

Run directly with unittest to avoid application/bootstrap pytest fixtures.
Only application imports and connection factories are replaced; Alembic's
real ConfigParser performs the URL interpolation round trip under test.
"""

from contextlib import ExitStack, nullcontext
from pathlib import Path
import os
import runpy
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from alembic import context
from alembic.config import Config
from sqlalchemy.engine import make_url


BACKEND = Path(__file__).resolve().parents[1]
PASSWORDS = ("demo%value", "demo!value", "demo@value", "demo:value", "demo/value", "demo%25!@:/value")


def synthetic_url(password):
    return "postgresql+psycopg2://unit%40example:" + quote(password, safe="") + "@example.invalid/geovision?sslmode=require&application_name=geo%20vision"


class AlembicUrlInterpolationTests(unittest.TestCase):
    def execute_environment(self, *, url, accounts=False, offline=False, provided_connection=None):
        configuration = Config()
        if provided_connection is not None:
            configuration.attributes["connection"] = provided_connection
        app = ModuleType("app")
        app.__path__ = []
        database = ModuleType("app.database")
        database.Base = SimpleNamespace(metadata=object())
        models = ModuleType("app.models")
        settings = ModuleType("app.config")
        settings.DATABASE_URL = url
        app.models = models
        with ExitStack() as stack:
            stack.enter_context(patch.dict(sys.modules, {"app": app, "app.database": database, "app.models": models, "app.config": settings}))
            stack.enter_context(patch.object(sys, "path", list(sys.path)))
            stack.enter_context(patch.dict(os.environ, {"ACCOUNTS_DATABASE_URL": url}))
            stack.enter_context(patch.object(context, "config", configuration, create=True))
            stack.enter_context(patch.object(context, "is_offline_mode", return_value=offline))
            configured = stack.enter_context(patch.object(context, "configure"))
            stack.enter_context(patch.object(context, "begin_transaction", return_value=nullcontext()))
            migrations = stack.enter_context(patch.object(context, "run_migrations"))
            factory = stack.enter_context(patch("sqlalchemy.create_engine" if accounts else "sqlalchemy.engine_from_config"))
            environment = BACKEND / ("accounts_alembic" if accounts else "alembic") / "env.py"
            runpy.run_path(str(environment))
        migrations.assert_called_once_with()
        return configuration, configured, factory

    def test_real_config_rejects_unescaped_percent_encoded_url(self):
        with self.assertRaises(ValueError):
            Config().set_main_option("sqlalchemy.url", synthetic_url("demo%value"))

    def test_primary_offline_preserves_url_and_decoded_password(self):
        for password in PASSWORDS:
            with self.subTest(password=password):
                url = synthetic_url(password)
                config, configured, factory = self.execute_environment(url=url, offline=True)
                self.assertEqual(config.get_main_option("sqlalchemy.url"), url)
                self.assertEqual(config.get_section(config.config_ini_section)["sqlalchemy.url"], url)
                self.assertEqual(config.file_config.get(config.config_ini_section, "sqlalchemy.url", raw=True), url.replace("%", "%%"))
                self.assertEqual(configured.call_args.kwargs["url"], url)
                self.assertEqual(make_url(configured.call_args.kwargs["url"]).password, password)
                factory.assert_not_called()

    def test_primary_online_passes_original_url_to_sqlalchemy(self):
        for password in PASSWORDS:
            with self.subTest(password=password):
                url = synthetic_url(password)
                _, configured, factory = self.execute_environment(url=url)
                factory.assert_called_once()
                runtime_url = factory.call_args.args[0]["sqlalchemy.url"]
                self.assertEqual(runtime_url, url)
                self.assertEqual(make_url(runtime_url).password, password)
                self.assertEqual(make_url(runtime_url).username, "unit@example")
                self.assertEqual(make_url(runtime_url).query["application_name"], "geo vision")
                self.assertIn("connection", configured.call_args.kwargs)

    def test_accounts_direct_url_does_not_get_configparser_escaping(self):
        for password in PASSWORDS:
            for offline in (False, True):
                with self.subTest(password=password, offline=offline):
                    url = synthetic_url(password)
                    _, configured, factory = self.execute_environment(url=url, accounts=True, offline=offline)
                    if offline:
                        runtime_url = configured.call_args.kwargs["url"]
                        factory.assert_not_called()
                    else:
                        factory.assert_called_once()
                        runtime_url = factory.call_args.args[0]
                        self.assertTrue(factory.call_args.kwargs["hide_parameters"])
                    self.assertEqual(runtime_url, url)
                    self.assertEqual(make_url(runtime_url).password, password)

    def test_accounts_provided_connection_still_bypasses_url_factory(self):
        supplied = MagicMock(name="disposable_connection")
        _, configured, factory = self.execute_environment(url="", accounts=True, provided_connection=supplied)
        factory.assert_not_called()
        self.assertIs(configured.call_args.kwargs["connection"], supplied)


if __name__ == "__main__":
    unittest.main()
