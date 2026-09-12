"""Standalone startup log-safety checks; no settings, secrets or DB are loaded.

Run directly with Python's standard library so the legacy pytest conftest does
not initialize application settings or persistence during these isolated tests.
"""

import contextlib
import importlib.util
import io
import subprocess
import sys
import traceback
import types
import unittest
from pathlib import Path
from unittest import mock


_START_PATH = Path(__file__).resolve().parents[1] / "start.py"
_SECRET_MARKER = "GEOVISION_SYNTHETIC_MIGRATION_SECRET_DO_NOT_LOG"
_SYNTHETIC_URL = (
    f"postgresql://pilot:{_SECRET_MARKER}%25@database.invalid/synthetic"
)


def _load_isolated_start():
    """Import the real startup code with inert, explicitly synthetic settings."""

    config = types.ModuleType("app.core.config")
    config.settings = types.SimpleNamespace(
        migrate_timeout_seconds=31,
        run_migrations_on_startup=True,
        startup_compatibility_bootstrap=True,
    )
    integration = types.ModuleType("app.core.integration")
    integration.sanitize_integration_message = lambda _value: "[redacted]"
    spec = importlib.util.spec_from_file_location(
        "geovision_start_log_safety_test", _START_PATH
    )
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(
        sys.modules,
        {"app.core.config": config, "app.core.integration": integration},
    ):
        spec.loader.exec_module(module)
    return module


class StartupMigrationRedactionTests(unittest.TestCase):
    def setUp(self):
        self.start = _load_isolated_start()
        self.repair = mock.Mock()
        self.start._ensure_schema_columns = self.repair

    def invoke_safely(self, function):
        stdout, stderr = io.StringIO(), io.StringIO()
        stopped = None
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                function()
            except SystemExit as exc:
                stopped = exc
        rendered = ""
        if stopped is not None:
            rendered = "".join(
                traceback.format_exception(
                    type(stopped), stopped, stopped.__traceback__
                )
            )
            self.assertEqual(stopped.code, 1)
            self.assertTrue(stopped.__suppress_context__)
            self.assertIsNone(stopped.__cause__)
        for text in (stdout.getvalue(), stderr.getvalue(), rendered):
            self.assertNotIn(_SECRET_MARKER, text)
            self.assertNotIn(_SYNTHETIC_URL, text)
        return stdout.getvalue(), stderr.getvalue(), stopped

    def test_success_captures_both_streams_and_preserves_timeout_and_repair(self):
        result = subprocess.CompletedProcess(
            ["alembic"], 0, stdout=_SYNTHETIC_URL, stderr=_SYNTHETIC_URL
        )
        with mock.patch.object(self.start.subprocess, "run", return_value=result) as run:
            stdout, stderr, stopped = self.invoke_safely(self.start._run_migrations)
        run.assert_called_once_with(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            check=True,
            cwd=self.start._BACKEND_ROOT,
            timeout=31,
            capture_output=True,
        )
        self.assertIsNone(stopped)
        self.assertEqual(stderr, "")
        self.assertIn("Migrations complete.", stdout)
        self.repair.assert_called_once_with()

    def test_called_process_error_never_exposes_captured_payload_or_command(self):
        for payload in (_SYNTHETIC_URL, _SYNTHETIC_URL.encode()):
            with self.subTest(payload_type=type(payload).__name__):
                error = subprocess.CalledProcessError(
                    1, ["alembic", _SYNTHETIC_URL], output=payload, stderr=payload
                )
                with mock.patch.object(self.start.subprocess, "run", side_effect=error):
                    stdout, stderr, stopped = self.invoke_safely(
                        self.start._run_migrations
                    )
                self.assertIsNotNone(stopped)
                self.assertIn("Alembic upgrade failed.", stderr)
                self.assertNotIn("Migrations complete.", stdout)
                self.repair.assert_not_called()

    def test_timeout_never_exposes_captured_payload_or_command(self):
        for payload in (_SYNTHETIC_URL, _SYNTHETIC_URL.encode()):
            with self.subTest(payload_type=type(payload).__name__):
                error = subprocess.TimeoutExpired(
                    ["alembic", _SYNTHETIC_URL], 31, output=payload, stderr=payload
                )
                with mock.patch.object(self.start.subprocess, "run", side_effect=error):
                    stdout, stderr, stopped = self.invoke_safely(
                        self.start._run_migrations
                    )
                self.assertIsNotNone(stopped)
                self.assertIn("Alembic migrations timed out.", stderr)
                self.assertNotIn("Migrations complete.", stdout)
                self.repair.assert_not_called()

    def test_launch_error_is_safe_and_fails_closed(self):
        with mock.patch.object(
            self.start.subprocess, "run", side_effect=OSError(_SYNTHETIC_URL)
        ):
            _, stderr, stopped = self.invoke_safely(self.start._run_migrations)
        self.assertIsNotNone(stopped)
        self.assertIn("Alembic upgrade failed.", stderr)
        self.repair.assert_not_called()

    def test_primary_failure_stops_accounts_bootstrap_and_server(self):
        for command in ("migrate", "serve"):
            with self.subTest(command=command):
                self.start._run_accounts_migrations = mock.Mock()
                self.start._run_compatibility_bootstrap = mock.Mock()
                self.start._serve = mock.Mock()
                error = subprocess.CalledProcessError(
                    1, ["alembic"], output=_SYNTHETIC_URL, stderr=_SYNTHETIC_URL
                )
                with mock.patch.object(self.start.subprocess, "run", side_effect=error):
                    _, _, stopped = self.invoke_safely(
                        lambda: self.start.main((command,))
                    )
                self.assertIsNotNone(stopped)
                self.repair.assert_not_called()
                self.start._run_accounts_migrations.assert_not_called()
                self.start._run_compatibility_bootstrap.assert_not_called()
                self.start._serve.assert_not_called()

    def test_success_preserves_migration_job_order_without_serving(self):
        calls = []
        self.start._ensure_schema_columns = lambda: calls.append("repair")
        self.start._run_accounts_migrations = lambda: calls.append("accounts")
        self.start._run_compatibility_bootstrap = lambda: calls.append("bootstrap")
        self.start._serve = mock.Mock()

        def successful_primary(*_args, **_kwargs):
            calls.append("primary")
            return subprocess.CompletedProcess(["alembic"], 0)

        with mock.patch.object(
            self.start.subprocess, "run", side_effect=successful_primary
        ):
            _, _, stopped = self.invoke_safely(lambda: self.start.main(("migrate",)))
        self.assertIsNone(stopped)
        self.assertEqual(calls, ["primary", "repair", "accounts", "bootstrap"])
        self.start._serve.assert_not_called()

    def test_real_child_output_is_captured_on_success_and_failure(self):
        real_run = subprocess.run
        for exit_code in (0, 1):
            with self.subTest(exit_code=exit_code):
                self.repair.reset_mock()
                child_code = (
                    "import sys; "
                    f"print({_SYNTHETIC_URL!r}, flush=True); "
                    f"print({_SYNTHETIC_URL!r}, file=sys.stderr, flush=True); "
                    f"sys.exit({exit_code})"
                )

                def synthetic_child(_command, **kwargs):
                    self.assertTrue(kwargs.get("capture_output"))
                    return real_run(
                        [sys.executable, "-c", child_code],
                        env={"PYTHONNOUSERSITE": "1"},
                        **kwargs,
                    )

                with mock.patch.object(
                    self.start.subprocess, "run", side_effect=synthetic_child
                ):
                    _, _, stopped = self.invoke_safely(self.start._run_migrations)
                self.assertEqual(stopped is None, exit_code == 0)
                self.assertEqual(self.repair.called, exit_code == 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
