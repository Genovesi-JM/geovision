"""Offline pilot policy evaluation; no Azure session or application imports."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_contract import AZURE_ROOT
from test_provider_bindings import CLI


class PilotProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path(CLI).is_file():
            raise unittest.SkipTest("Bicep CLI required")

    def evaluate(self, parameters):
        with tempfile.TemporaryDirectory(prefix="gv-pilot-policy-") as temporary:
            fixture = Path(temporary) / "profile.bicepparam"
            module = os.path.relpath(AZURE_ROOT / "modules/workload-profile.bicep", fixture.parent)
            fixture.write_text(f"using '{module}'\n" + parameters)
            result = subprocess.run([CLI, "snapshot", str(fixture), "--mode", "overwrite"],
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            snapshot = json.loads(fixture.with_suffix(".snapshot.json").read_text())
            self.assertEqual(snapshot["diagnostics"], [])
            self.assertEqual(snapshot["predictedResources"], [])
            return snapshot["outputs"]

    def test_pilot_uses_deployed_validation_real_database_queue_and_only_event_worker(self):
        result = self.evaluate("param deploymentProfile = 'pilot'\nparam apiMinReplicas = 0\n")
        self.assertTrue(result["pilotEnabled"])
        self.assertEqual(result["runtimeEnvironment"], "staging")
        self.assertEqual(result["queueProvider"], "database")
        self.assertFalse(result["serviceBusEnabled"])
        self.assertEqual(result["appConfigurationSku"], "free")
        self.assertEqual(result["apiMinReplicas"], 0)
        self.assertTrue(result["eventEnabled"])
        for name in ("erp", "notification", "processing", "intelligence"):
            self.assertFalse(result[f"{name}Enabled"])

    def test_standard_defaults_unchanged_and_worker_flags_independent(self):
        standard = self.evaluate("")
        self.assertEqual(standard["queueProvider"], "azure_service_bus")
        self.assertTrue(standard["serviceBusEnabled"])
        self.assertEqual(standard["apiMinReplicas"], 1)
        for name in ("event", "erp", "notification", "processing", "intelligence"):
            self.assertTrue(standard[f"{name}Enabled"])
        configured = self.evaluate("param environmentName = 'staging'\nparam workers = { erp: false, notification: false }\n")
        self.assertFalse(configured["erpEnabled"])
        self.assertFalse(configured["notificationEnabled"])
        self.assertTrue(configured["eventEnabled"])
        self.assertTrue(configured["processingEnabled"])

    def test_pilot_or_disabled_flags_cannot_weaken_production(self):
        result = self.evaluate("param deploymentProfile = 'pilot'\nparam environmentName = 'prod'\nparam apiMinReplicas = 0\nparam apiMaxReplicas = 2\nparam workers = { event: false, erp: false, notification: false, processing: false, intelligence: false }\n")
        self.assertFalse(result["pilotEnabled"])
        self.assertEqual(result["runtimeEnvironment"], "prod")
        self.assertTrue(result["serviceBusEnabled"])
        self.assertEqual(result["queueProvider"], "azure_service_bus")
        self.assertEqual(result["appConfigurationSku"], "standard")
        self.assertEqual(result["apiMinReplicas"], 2)
        self.assertEqual(result["apiMaxReplicas"], 10)
        for name in ("event", "erp", "notification", "processing", "intelligence"):
            self.assertTrue(result[f"{name}Enabled"])

    def test_resource_and_secret_contracts(self):
        environment = (AZURE_ROOT / "environment.bicep").read_text()
        apps = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        vault = (AZURE_ROOT / "modules/key-vault.bicep").read_text()
        postgres = (AZURE_ROOT / "modules/postgres.bicep").read_text()
        rbac = (AZURE_ROOT / "modules/rbac.bicep").read_text()
        self.assertIn("module serviceBus './modules/service-bus.bicep' = if (!pilot)", environment)
        self.assertIn("serviceBusEnabled: !pilot", environment)
        self.assertEqual(rbac.count("= if (serviceBusEnabled)"), 2)
        self.assertIn("name: 'ACCOUNTS_DATABASE_URL'", apps)
        self.assertIn("secretRef: 'accounts-database-url'", apps)
        self.assertIn("name: 'accounts-database-url'", vault)
        self.assertIn("uriComponent(accountsDatabaseName)", vault)
        self.assertIn("resource accountsDatabase ", postgres)
        for worker in ("event", "erp", "notification", "processing", "intelligence"):
            self.assertIn(f"if (deployApplications && {worker}WorkerEnabled)", apps)
        self.assertIn("value: queueProvider", apps)
        for name in ("eventWorker", "erpWorker", "notificationWorker", "processingWorker", "intelligenceWorker"):
            block = apps.split(f"resource {name} ", 1)[1].split("\nresource ", 1)[0]
            self.assertNotIn("accountsSecretConfiguration", block)
            self.assertNotIn("accountsEnvironment", block)
        for name in ("api", "migrationJob"):
            block = apps.split(f"resource {name} ", 1)[1].split("\nresource ", 1)[0]
            self.assertIn("accountsSecretConfiguration", block)
            self.assertIn("accountsEnvironment", block)

    def test_pilot_helper_targets_its_own_group_and_never_sources_credential_files(self):
        helper = (AZURE_ROOT / "deploy.sh").read_text()
        parameters = (AZURE_ROOT / "pilot.bicepparam").read_text()
        self.assertIn("AZURE_DEPLOYMENT_PROFILE", helper)
        self.assertIn('rg-geovision-${default_profile_name}-weu', helper)
        self.assertIn("param environmentName = 'staging'", parameters)
        self.assertIn("param resourceGroupName = 'rg-geovision-pilot-weu'", parameters)
        self.assertIn("param providerConfiguration = {}", parameters)
        self.assertIn("param location = 'spaincentral'", parameters)
        self.assertIn("param resourceGroupLocation = 'westeurope'", parameters)
        self.assertIn("param apiExternalIngress = false", parameters)
        self.assertIn("param deployConfigurationValues = false", parameters)
        self.assertNotIn("source .env", helper)

    def test_free_app_configuration_omits_unsupported_soft_delete(self):
        source = (AZURE_ROOT / "modules/app-configuration.bicep").read_text()
        self.assertIn("disableLocalAuth: true", source)
        self.assertIn("skuName == 'standard' ? {", source)
        self.assertIn("softDeleteRetentionInDays: 7", source)
        self.assertIn("} : {})", source)
        self.assertIn("authenticationMode: 'Pass-through'", source)
        self.assertIn("if (deployValues)", source)

    def test_pilot_ingress_is_separate_from_application_creation(self):
        main = (AZURE_ROOT / "main.bicep").read_text()
        apps = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        self.assertIn("param apiExternalIngress bool = deploymentProfile == 'pilot' && environmentName != 'prod' ? false : true", main)
        self.assertIn("external: apiExternalIngress", apps)
        self.assertNotIn("external: true", apps)

    def test_checked_in_pilot_parameters_compile_with_only_invented_secret_inputs(self):
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GEOVISION_POSTGRES_ADMIN_PASSWORD": "fixture-only-password-never-deploy",
            "GEOVISION_SECRET_KEY": "fixture-only-signing-key-never-deploy-00000000",
            "GEOVISION_ENCRYPTION_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        }
        result = subprocess.run(
            [CLI, "build-params", str(AZURE_ROOT / "pilot.bicepparam"), "--stdout"],
            capture_output=True, text=True, timeout=40, env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
