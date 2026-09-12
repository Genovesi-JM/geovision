"""Actual accounts migrations on disposable SQLite, plus isolated startup checks.

No app/settings import, root pytest conftest, .env, existing database or network.
PostgreSQL restore/DDL execution remains a separate staging gate.
"""

import ast
from contextlib import redirect_stderr
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from test_contract import REPO_ROOT


BACKEND = REPO_ROOT / "backend"


def migration_config(connection=None):
    config = Config(str(BACKEND / "accounts_alembic.ini"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


class AccountsMigrationTests(unittest.TestCase):
    def test_clean_upgrade_repeated_upgrade_and_unique_constraints(self):
        with tempfile.TemporaryDirectory(prefix="gv-accounts-test-") as temporary:
            engine = create_engine(f"sqlite:///{temporary}/accounts.db")
            with engine.begin() as connection:
                config = migration_config(connection)
                command.upgrade(config, "head")
                self.assertEqual(set(inspect(connection).get_table_names()), {"alembic_version", "customer_accounts", "employees"})
                connection.execute(text("INSERT INTO customer_accounts (name,email,created_at) VALUES ('Synthetic','fixture@example.invalid',CURRENT_TIMESTAMP)"))
                command.upgrade(config, "head")
                self.assertEqual(connection.scalar(text("SELECT count(*) FROM customer_accounts")), 1)
                self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "accounts_v1")
                self.assertTrue(any(index["unique"] and index["column_names"] == ["email"] for index in inspect(connection).get_indexes("employees")))
            engine.dispose()

    def test_existing_unversioned_tables_are_not_silently_adopted(self):
        with tempfile.TemporaryDirectory(prefix="gv-accounts-legacy-") as temporary:
            engine = create_engine(f"sqlite:///{temporary}/accounts.db")
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE customer_accounts (id INTEGER PRIMARY KEY, original TEXT)"))
                connection.execute(text("INSERT INTO customer_accounts VALUES (1,'preserve')"))
                with self.assertRaises(Exception):
                    command.upgrade(migration_config(connection), "head")
                self.assertEqual(connection.scalar(text("SELECT original FROM customer_accounts WHERE id=1")), "preserve")
            engine.dispose()

    def test_postgresql_offline_ddl_uses_separate_versioned_tables(self):
        output = io.StringIO()
        config = migration_config()
        config.output_buffer = output
        with patch.dict(os.environ, {"ACCOUNTS_DATABASE_URL": "postgresql://fixture:fixture@db.invalid/accounts"}, clear=True):
            command.upgrade(config, "head", sql=True)
        ddl = output.getvalue()
        for expected in ("CREATE TABLE customer_accounts", "CREATE TABLE employees", "accounts_v1", "CREATE UNIQUE INDEX ix_employees_email"):
            self.assertIn(expected, ddl)

    def test_missing_connection_fails_closed_without_reading_dotenv(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "ACCOUNTS_DATABASE_URL is required"):
                command.upgrade(migration_config(), "head")

    def test_accounts_readiness_checks_its_own_packaged_head_and_rejects_sqlite(self):
        spec = importlib.util.spec_from_file_location("isolated_readiness", BACKEND / "app/core/readiness.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.expected_migration_heads(BACKEND / "accounts_alembic.ini"), frozenset({"accounts_v1"}))
        engine = create_engine("sqlite://")
        with self.assertRaisesRegex(RuntimeError, "must use PostgreSQL"):
            module.assert_accounts_database_ready(engine)
        fake = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        with patch.object(module, "assert_database_ready") as assertion:
            module.assert_accounts_database_ready(fake)
            assertion.assert_called_once_with(fake, require_current_schema=True, config_path=BACKEND / "accounts_alembic.ini")

    def test_startup_migration_order_and_secret_free_failure(self):
        tree = ast.parse((BACKEND / "start.py").read_text())
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        calls = {name: min(node.lineno for node in ast.walk(functions["main"])
                           if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name)
                 for name in ("_run_migrations", "_run_accounts_migrations", "_run_compatibility_bootstrap")}
        self.assertLess(calls["_run_migrations"], calls["_run_accounts_migrations"])
        self.assertLess(calls["_run_accounts_migrations"], calls["_run_compatibility_bootstrap"])
        settings = SimpleNamespace(database_url="postgresql://fixture:fixture@db.invalid/primary", accounts_database_url="postgresql://fixture:fixture@db.invalid/accounts", is_deployed=True, migrate_timeout_seconds=10)
        namespace = {"settings": settings, "subprocess": subprocess, "sys": sys, "os": os, "_BACKEND_ROOT": BACKEND}
        exec(compile(ast.Module(body=[functions["_run_accounts_migrations"]], type_ignores=[]), "isolated-start", "exec"), namespace)
        with patch.object(subprocess, "run") as run:
            namespace["_run_accounts_migrations"]()
            self.assertTrue(run.call_args.kwargs["capture_output"])
            self.assertNotIn(settings.accounts_database_url, run.call_args.args[0])
        error_output = io.StringIO()
        with patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["alembic"], stderr=settings.accounts_database_url)):
            with redirect_stderr(error_output), self.assertRaises(SystemExit):
                namespace["_run_accounts_migrations"]()
        self.assertIn("runtime rollout is stopped", error_output.getvalue())
        self.assertNotIn(settings.accounts_database_url, error_output.getvalue())
        settings.accounts_database_url = "postgresql://another:another@db.invalid:5432/primary?sslmode=require"
        with patch.object(subprocess, "run") as run:
            with self.assertRaises(SystemExit):
                namespace["_run_accounts_migrations"]()
            run.assert_not_called()
        settings.accounts_database_url = "sqlite:///forbidden.db"
        with self.assertRaises(SystemExit):
            namespace["_run_accounts_migrations"]()
