"""Offline checks for release-coordinated database secret references.

Container Apps documents versioned URIs for explicit version control:
https://learn.microsoft.com/azure/container-apps/manage-secrets
No Azure login, secret values, parameter files or application imports are used.
"""

import json
from pathlib import Path
import subprocess
import unittest

from test_contract import AZURE_ROOT
from test_provider_bindings import CLI


class DatabaseSecretVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not Path(CLI).is_file():
            raise unittest.SkipTest("Bicep CLI required")
        result = subprocess.run(
            [CLI, "build", str(AZURE_ROOT / "modules/key-vault.bicep"), "--stdout"],
            capture_output=True,
            text=True,
            timeout=40,
        )
        if result.returncode != 0 or "BCP053" in result.stderr:
            raise AssertionError(result.stderr)
        cls.template = json.loads(result.stdout)

    def test_both_database_outputs_reference_the_written_secret_version(self):
        for output_name, secret_name in (
            ("databaseUrlSecretUri", "database-url"),
            ("accountsDatabaseUrlSecretUri", "accounts-database-url"),
        ):
            with self.subTest(output=output_name):
                self.assertEqual(
                    self.template["outputs"][output_name],
                    {
                        "type": "string",
                        "value": (
                            "[reference(resourceId('Microsoft.KeyVault/vaults/secrets', "
                            f"parameters('keyVaultName'), '{secret_name}'), "
                            "'2023-07-01').secretUriWithVersion]"
                        ),
                    },
                )

    def test_signing_and_encryption_references_remain_unchanged(self):
        for output_name, secret_name in (
            ("secretKeySecretUri", "secret-key"),
            ("encryptionKeySecretUri", "encryption-key"),
        ):
            with self.subTest(output=output_name):
                self.assertEqual(
                    self.template["outputs"][output_name]["value"],
                    "[format('{0}secrets/{1}', "
                    "reference(resourceId('Microsoft.KeyVault/vaults', "
                    "parameters('keyVaultName')), '2023-07-01').vaultUri, "
                    f"'{secret_name}')]",
                )

    def test_outputs_export_metadata_not_secret_values(self):
        outputs = json.dumps(self.template["outputs"])
        self.assertEqual(outputs.count("secretUriWithVersion"), 2)
        self.assertNotIn(".value", outputs)
        self.assertNotIn("list", outputs.lower())
        for parameter_name in (
            "postgresAdministratorPassword", "secretKey", "encryptionKey"
        ):
            self.assertEqual(
                self.template["parameters"][parameter_name]["type"].lower(),
                "securestring",
            )
            self.assertNotIn(f"parameters('{parameter_name}')", outputs)
        for variable_name in ("databaseUrl", "accountsDatabaseUrl"):
            self.assertNotIn(f"variables('{variable_name}')", outputs)

    def test_existing_consumer_wiring_passes_both_uris_without_stripping_version(self):
        environment = (AZURE_ROOT / "environment.bicep").read_text()
        applications = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        for parameter_name in ("databaseUrlSecretUri", "accountsDatabaseUrlSecretUri"):
            self.assertIn(
                f"{parameter_name}: keyVault.outputs.{parameter_name}", environment
            )
            self.assertIn(f"keyVaultUrl: {parameter_name}", applications)
        migration_job = applications.split("resource migrationJob ", 1)[1]
        self.assertIn("accountsSecretConfiguration", migration_job)
        self.assertIn("secretConfiguration", migration_job)

    def test_complete_parent_template_compiles_offline(self):
        result = subprocess.run(
            [CLI, "build", str(AZURE_ROOT / "main.bicep"), "--stdout"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        json.loads(result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
