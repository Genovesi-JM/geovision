from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
AZURE_ROOT = REPO_ROOT / "infra" / "azure"


def _settings_fields() -> set[str]:
    tree = ast.parse((REPO_ROOT / "backend/app/core/config.py").read_text())
    settings = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
    )
    return {
        statement.target.id.upper()
        for statement in settings.body
        if isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
    }


class AzureTemplateContractTests(unittest.TestCase):
    def test_container_environment_names_match_settings_contract(self) -> None:
        template = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        configured_names = set(re.findall(r"name: '([A-Z][A-Z0-9_]+)'", template))
        settings_names = _settings_fields()
        unknown = configured_names - settings_names
        self.assertEqual(unknown, set(), f"unknown backend settings: {sorted(unknown)}")

    def test_app_configuration_names_match_settings_contract(self) -> None:
        template = (AZURE_ROOT / "modules/app-configuration.bicep").read_text()
        configured_names = set(re.findall(r"name: '([A-Z][A-Z0-9_]+)'", template))
        settings_names = _settings_fields()
        unknown = configured_names - settings_names
        self.assertEqual(unknown, set(), f"unknown backend settings: {sorted(unknown)}")

    def test_service_bus_namespace_is_a_bare_hostname(self) -> None:
        template = (AZURE_ROOT / "modules/service-bus.bicep").read_text()
        self.assertIn("${serviceBus.name}.servicebus.windows.net", template)
        self.assertNotIn(
            "output fullyQualifiedNamespace string = serviceBus.properties.serviceBusEndpoint",
            template,
        )

    def test_image_bootstrap_and_release_gates_are_independent(self) -> None:
        root_template = (AZURE_ROOT / "main.bicep").read_text()
        apps_template = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        self.assertIn("param deployApplications bool = false", root_template)
        self.assertIn("param deployMigrationJob bool = deployApplications", root_template)
        self.assertIn("if (deployApplications)", apps_template)
        self.assertIn("if (deployMigrationJob)", apps_template)

    def test_data_plane_local_auth_is_disabled(self) -> None:
        templates = {
            name: (AZURE_ROOT / "modules" / name).read_text()
            for name in (
                "app-configuration.bicep",
                "registry.bicep",
                "service-bus.bicep",
                "storage.bicep",
            )
        }
        self.assertIn("disableLocalAuth: true", templates["app-configuration.bicep"])
        self.assertIn("adminUserEnabled: false", templates["registry.bicep"])
        self.assertIn("disableLocalAuth: true", templates["service-bus.bicep"])
        self.assertIn("allowSharedKeyAccess: false", templates["storage.bicep"])

    def test_migration_precedes_readiness_gated_api_contract(self) -> None:
        template = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        for expected in (
            "'start.py'\n            'migrate'",
            "'start.py'\n            'serve'\n            '--skip-migrations'",
            "name: 'STARTUP_COMPATIBILITY_BOOTSTRAP'",
            "name: 'READINESS_REQUIRE_CURRENT_SCHEMA'",
        ):
            self.assertIn(expected, template)


if __name__ == "__main__":
    unittest.main()
