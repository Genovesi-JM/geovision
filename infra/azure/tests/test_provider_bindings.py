"""Offline provider wiring tests; snapshots evaluate ARM expressions without Azure.

Fixtures contain only public dummy vault/identity references, never credentials.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_contract import AZURE_ROOT, REPO_ROOT, _settings_fields


FIXTURES = AZURE_ROOT / "tests/fixtures"
MODULE = AZURE_ROOT / "modules/provider-bindings.bicep"
VAULT = "https://kv-geovision-fixture.vault.azure.net/"
IDENTITY = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/fixture"
    "/providers/Microsoft.ManagedIdentity/userAssignedIdentities/fixture"
)
RUNTIMES = ("api", "event", "notification", "processing", "intelligence")
CLI = (
    os.environ.get("BICEP_BIN")
    or shutil.which("bicep")
    or str(Path.home() / ".azure/bin/bicep")
)


def snapshot(name: str) -> dict:
    return json.loads((FIXTURES / f"providers-{name}.snapshot.json").read_text())


def named(entries: list[dict]) -> dict[str, dict]:
    return {entry["name"]: entry for entry in entries}


class ProviderBindingContractTests(unittest.TestCase):
    def test_all_fixture_outputs_are_resource_free_and_match_settings(self) -> None:
        for profile in ("default", "all", "conservative"):
            record = snapshot(profile)
            self.assertEqual(record["predictedResources"], [])
            self.assertEqual(record["diagnostics"], [])
            for runtime in RUNTIMES:
                entries = record["outputs"][f"{runtime}Environment"]
                self.assertTrue(set(named(entries)) <= _settings_fields())

    def test_default_preserves_existing_runtime_values_and_has_no_provider_secrets(self) -> None:
        outputs = snapshot("default")["outputs"]
        self.assertEqual(outputs["apiEnvironment"], [])
        self.assertEqual(outputs["eventEnvironment"], [])
        self.assertEqual(outputs["notificationEnvironment"], [
            {"name": "NOTIFICATION_PROVIDER", "value": "auto"},
        ])
        self.assertEqual(outputs["processingEnvironment"], [
            {"name": "PROCESSING_PROVIDER", "value": "none"},
        ])
        self.assertEqual(outputs["intelligenceEnvironment"], [
            {"name": "SATELLITE_PROVIDER", "value": "none"},
            {"name": "WEATHER_PROVIDER", "value": "none"},
        ])
        for runtime in RUNTIMES:
            self.assertEqual(outputs[f"{runtime}Secrets"], [])

    def test_all_enabled_has_unique_names_no_core_overrides_and_resolved_references(self) -> None:
        apps = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        common = apps[apps.index("var commonEnvironment"):apps.index("resource managedEnvironment")]
        core_names = set(re.findall(r"name: '([A-Z][A-Z0-9_]+)'", common))
        outputs = snapshot("all")["outputs"]
        for runtime in RUNTIMES:
            environment = outputs[f"{runtime}Environment"]
            secrets = outputs[f"{runtime}Secrets"]
            env_names = [entry["name"] for entry in environment]
            secret_names = [entry["name"] for entry in secrets]
            self.assertEqual(len(env_names), len(set(env_names)), runtime)
            self.assertEqual(len(secret_names), len(set(secret_names)), runtime)
            self.assertFalse(set(env_names) & core_names)
            self.assertFalse(set(secret_names) & {"database-url", "secret-key", "encryption-key"})
            used_secrets = {entry["secretRef"] for entry in environment if "secretRef" in entry}
            self.assertEqual(used_secrets, set(secret_names), runtime)
            for secret in secrets:
                self.assertEqual(set(secret), {"name", "identity", "keyVaultUrl"})
                self.assertEqual(secret["identity"], IDENTITY)
                self.assertEqual(secret["keyVaultUrl"], f"{VAULT}secrets/{secret['name']}")

    def test_credentials_are_references_and_do_not_spread_to_unrelated_workers(self) -> None:
        outputs = snapshot("all")["outputs"]
        api = named(outputs["apiEnvironment"])
        for name in (
            "GOOGLE_MAPS_SERVER_API_KEY", "AEMET_API_KEY", "COPERNICUS_ACCESS_TOKEN",
            "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "NODEODM_BASE_URL", "NODEODM_TOKEN",
        ):
            self.assertIn("secretRef", api[name])
            self.assertNotIn("value", api[name])
        self.assertEqual(set(named(outputs["eventSecrets"])), {"provider-nodeodm-url"})
        self.assertEqual(set(named(outputs["processingSecrets"])), {
            "provider-nodeodm-url", "provider-nodeodm-token",
        })
        self.assertEqual(set(named(outputs["intelligenceSecrets"])), {
            "provider-aemet-key", "provider-copernicus-token",
        })
        self.assertEqual(set(named(outputs["notificationSecrets"])), {
            "provider-smtp-host", "provider-smtp-user", "provider-smtp-password", "provider-smtp-from",
        })

    def test_conservative_flags_do_not_enable_downloads_traffic_or_automatic_processing(self) -> None:
        outputs = snapshot("conservative")["outputs"]
        api = named(outputs["apiEnvironment"])
        for name in (
            "GOOGLE_ROUTES_TRAFFIC_AWARE", "SATELLITE_DOWNLOAD_ASSETS_ENABLED", "PROCESSING_AUTO_CREATE_ENABLED",
        ):
            self.assertEqual(api[name]["value"], "false")
        for name in ("WEATHER_PROVIDER", "AEMET_API_KEY", "GIS_PROVIDER", "COPERNICUS_ACCESS_TOKEN"):
            self.assertNotIn(name, api)
        self.assertEqual(api["SMTP_PORT"]["value"], "587")
        self.assertEqual(api["SMTP_USE_TLS"]["value"], "true")
        all_api = named(snapshot("all")["outputs"]["apiEnvironment"])
        self.assertEqual(all_api["SMTP_PORT"]["value"], "2525")
        self.assertEqual(all_api["GOOGLE_ROUTES_TRAFFIC_AWARE"]["value"], "true")

    def test_event_worker_pins_smtp_deliveries_without_transport_credentials(self) -> None:
        # Exercise the real pure policy function without importing application
        # settings (which would load local .env files) or opening a database.
        source = REPO_ROOT / "backend/app/modules/notifications/materializer.py"
        tree = ast.parse(source.read_text())
        policy = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_email_provider")
        namespace = {"Settings": object, "settings": None}
        exec(compile(ast.Module(body=[policy], type_ignores=[]), str(source), "exec"), namespace)
        for profile, expected in (("default", "disabled"), ("all", "smtp"), ("conservative", "smtp")):
            entries = named(snapshot(profile)["outputs"]["eventEnvironment"])
            config = SimpleNamespace(
                notification_provider=entries.get("NOTIFICATION_PROVIDER", {}).get("value", "auto"),
                smtp_configuration_complete=False,
                is_deployed=True,
            )
            self.assertEqual(namespace["_email_provider"](config), expected)
            self.assertFalse(any(name.startswith("SMTP_") for name in entries))

    def test_configuration_flows_to_only_intended_runtime_blocks(self) -> None:
        root = (AZURE_ROOT / "main.bicep").read_text()
        environment = (AZURE_ROOT / "environment.bicep").read_text()
        apps = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        for text in (root, environment, apps):
            self.assertIn("param providerConfiguration FirstDemoProviderConfiguration = {}", text)
            self.assertIn("providerConfiguration: providerConfiguration", text)
        self.assertIn("providerKeyVaultUri: keyVault.outputs.vaultUri", environment)
        for symbol, output in (
            ("api", "api"), ("eventWorker", "event"),
            ("notificationWorker", "notification"), ("processingWorker", "processing"),
            ("intelligenceWorker", "intelligence"),
        ):
            block = apps.split(f"resource {symbol} ", 1)[1].split("\nresource ", 1)[0]
            self.assertIn(f"providerBindings.outputs.{output}Environment", block)
            self.assertIn(f"providerBindings.outputs.{output}Secrets", block)
        for symbol in ("erpWorker", "migrationJob"):
            block = apps.split(f"resource {symbol} ", 1)[1].split("\nresource ", 1)[0]
            self.assertNotIn("providerBindings.outputs", block)


class ProviderBindingCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not Path(CLI).is_file():
            if os.environ.get("GEOVISION_REQUIRE_BICEP_TESTS") == "1":
                raise AssertionError("Provider compiler tests require BICEP_BIN")
            raise unittest.SkipTest("Set BICEP_BIN to run offline Bicep snapshot/compiler tests")

    def test_snapshots_match_current_bicep_evaluation(self) -> None:
        for profile in ("default", "all", "conservative"):
            with self.subTest(profile=profile):
                result = subprocess.run(
                    [CLI, "snapshot", str(FIXTURES / f"providers-{profile}.bicepparam"), "--mode", "validate"],
                    capture_output=True, text=True, timeout=30, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sealed_contract_rejects_arbitrary_env_secrets_and_invalid_flags(self) -> None:
        invalid = (
            "{ DATABASE_URL: 'not-allowed' }",
            "{ googleMaps: { apiKey: 'not-allowed' } }",
            "{ aemet: 'true' }",
            "{ nodeOdm: { secretName: 'database-url' } }",
            "{ smtp: { port: 0 } }",
            "{ smtp: { port: 65536 } }",
            "{ smtp: { useTls: false } }",
            "{ copernicus: { vaultUri: 'https://untrusted.example/' } }",
            "{ stripe: {} }",
        )
        with tempfile.TemporaryDirectory(prefix="geovision-provider-contract-") as temporary:
            fixture = Path(temporary) / "invalid.bicepparam"
            module_path = os.path.relpath(MODULE, fixture.parent)
            for configuration in invalid:
                with self.subTest(configuration=configuration):
                    fixture.write_text(
                        f"using '{module_path}'\n"
                        f"param keyVaultUri = '{VAULT}'\n"
                        f"param identityResourceId = '{IDENTITY}'\n"
                        f"param providerConfiguration = {configuration}\n"
                    )
                    result = subprocess.run(
                        [CLI, "build-params", str(fixture), "--stdout"],
                        capture_output=True, text=True, timeout=30, check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRegex(result.stderr, r"Error BCP(037|036|327|328|334)")


if __name__ == "__main__":
    unittest.main()
