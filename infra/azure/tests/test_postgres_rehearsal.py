"""Offline safety checks for the opt-in Docker/PostGIS rehearsal harness."""

from types import SimpleNamespace
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from urllib.parse import quote, unquote, urlsplit

from verify_postgres_container import LABEL, Rehearsal


class RehearsalSafetyTests(unittest.TestCase):
    def test_docker_context_manifest_has_no_directory_or_glob_exceptions(self):
        backend = Path(__file__).resolve().parents[3] / "backend"
        entries = [line[1:] for line in (backend / ".dockerignore").read_text().splitlines()
                   if line.startswith("!")]
        self.assertTrue(entries)
        for entry in entries:
            self.assertFalse(any(character in entry for character in "*?[]"), entry)
            self.assertFalse(entry.endswith("/"), entry)
            self.assertFalse((backend / entry).is_symlink(), entry)
            self.assertTrue((backend / entry).is_file(), entry)
        for forbidden in ("app/private.env", "app/email_log.txt", "app/private.py", "app/schema.sql", ".env"):
            self.assertNotIn(forbidden, entries)

    def test_tracked_runtime_python_is_present_in_the_exact_manifest(self):
        repository = Path(__file__).resolve().parents[3]
        manifest = set((repository / "backend/.dockerignore").read_text().splitlines())
        result = subprocess.run(
            ["git", "ls-files", "--", "backend/app", "backend/alembic", "backend/accounts_alembic"],
            cwd=repository, text=True, capture_output=True, check=True,
        )
        for path in result.stdout.splitlines():
            if path.endswith(".py"):
                self.assertIn("!" + path[len("backend/"):], manifest, path)
        self.assertIn("!accounts_alembic/env.py", manifest)
        self.assertIn("!accounts_alembic/versions/accounts_v1.py", manifest)

    def test_database_targets_are_internal_fresh_fixtures(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        primary = urlsplit(rehearsal.env["DATABASE_URL"])
        accounts = urlsplit(rehearsal.env["ACCOUNTS_DATABASE_URL"])
        self.assertEqual((primary.hostname, accounts.hostname), ("db", "db"))
        self.assertEqual((primary.port, accounts.port), (5432, 5432))
        self.assertEqual((primary.path, accounts.path), ("/geovision", "/geovision_accounts"))
        self.assertEqual(rehearsal.env["ENV"], "staging")
        self.assertEqual(rehearsal.env["READINESS_REQUIRE_CURRENT_SCHEMA"], "true")
        self.assertNotIn("ADMIN_PASSWORD", rehearsal.env)

    def test_creating_container_does_not_publish_ports_mount_data_or_put_secrets_in_argv(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        with patch.object(rehearsal, "docker") as docker:
            rehearsal.create("fixture-job", "local-api", ["python", "start.py", "migrate"], env=rehearsal.env)
        args = docker.call_args.args[0]
        self.assertIn("--read-only", args)
        self.assertIn("--pull", args)
        self.assertIn("never", args)
        self.assertIn(LABEL + "=" + rehearsal.run_id, args)
        self.assertIn("--network", args)
        for prohibited in ("--publish", "-p", "--volume", "-v", "--mount", "--env-file"):
            self.assertNotIn(prohibited, args)
        for private_value in rehearsal.private_values:
            self.assertNotIn(private_value, " ".join(args))

    def test_special_character_password_is_encoded_once_for_both_databases(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        raw_password = rehearsal.pg_env["POSTGRES_PASSWORD"]
        for character in "% !@:/":
            self.assertIn(character, raw_password)
        encoded_password = quote(raw_password, safe="")
        self.assertNotEqual(encoded_password, raw_password)
        for setting, database in (("DATABASE_URL", "geovision"), ("ACCOUNTS_DATABASE_URL", "geovision_accounts")):
            with self.subTest(setting=setting):
                url = rehearsal.env[setting]
                parsed = urlsplit(url)
                self.assertEqual(url, "postgresql://fixture:" + encoded_password + "@db:5432/" + database)
                self.assertEqual(unquote(parsed.password), raw_password)
                self.assertEqual((parsed.username, parsed.hostname, parsed.port), ("fixture", "db", 5432))
                self.assertEqual((parsed.path, parsed.query, parsed.fragment), ("/" + database, "", ""))
                self.assertNotIn(raw_password, url)

    def test_failure_redacts_raw_encoded_and_configparser_password_forms(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        raw_password = rehearsal.pg_env["POSTGRES_PASSWORD"]
        encoded_password = quote(raw_password, safe="")
        escaped_password = encoded_password.replace("%", "%%")
        result = SimpleNamespace(returncode=1, stdout=raw_password + " " + encoded_password,
                                 stderr=escaped_password)
        with patch("verify_postgres_container.subprocess.run", return_value=result):
            with self.assertRaises(RuntimeError) as raised:
                rehearsal.docker(["synthetic-failure"])
        for value in (raw_password, encoded_password, escaped_password):
            self.assertNotIn(value, str(raised.exception))
        self.assertIn("[throwaway-value-redacted]", str(raised.exception))

    def test_cleanup_does_not_remove_a_label_mismatch(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        rehearsal.containers = ["fixture-job"]
        result = SimpleNamespace(returncode=0, stdout="another-run\n", stderr="")
        with patch.object(rehearsal, "docker", return_value=result) as docker:
            with self.assertRaisesRegex(RuntimeError, "label mismatch"):
                rehearsal.cleanup()
        self.assertEqual(docker.call_count, 1)
        self.assertEqual(docker.call_args.args[0][0], "inspect")

    def test_cleanup_reports_failure_instead_of_false_success(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        rehearsal.containers = ["fixture-job"]
        replies = [SimpleNamespace(returncode=0, stdout=rehearsal.run_id, stderr=""),
                   SimpleNamespace(returncode=1, stdout="", stderr="fixture removal failed")]
        with patch.object(rehearsal, "docker", side_effect=replies):
            with self.assertRaisesRegex(RuntimeError, "Cleanup incomplete"):
                rehearsal.cleanup()

    def test_wrong_architecture_stops_before_any_resource_creation(self):
        rehearsal = Rehearsal("local-api", "local-postgres")
        result = SimpleNamespace(returncode=0, stdout="arm64\n", stderr="")
        with patch.object(rehearsal, "docker", return_value=result) as docker:
            with self.assertRaisesRegex(RuntimeError, "amd64"):
                rehearsal.run()
        self.assertEqual(docker.call_count, 1)
        self.assertFalse(rehearsal.network_created)
        self.assertEqual(rehearsal.containers, [])


if __name__ == "__main__":
    unittest.main()
