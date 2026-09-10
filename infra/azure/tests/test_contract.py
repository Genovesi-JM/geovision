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

    def test_app_configuration_endpoint_is_wired_to_every_runtime(self) -> None:
        environment = (AZURE_ROOT / "environment.bicep").read_text()
        applications = (AZURE_ROOT / "modules/container-apps.bicep").read_text()
        app_configuration = (AZURE_ROOT / "modules/app-configuration.bicep").read_text()

        applications_block = environment[
            environment.index("module applications") : environment.index("output acrName")
        ]
        app_configuration_block = environment[
            environment.index("module appConfiguration") : environment.index(
                "module access"
            )
        ]
        self.assertIn(
            "appConfigurationEndpoint: appConfiguration.outputs.endpoint",
            applications_block,
        )
        self.assertNotIn("appConfigurationEndpoint:", app_configuration_block)
        self.assertIn("param appConfigurationEndpoint string", applications)
        self.assertIn("name: 'AZURE_APP_CONFIGURATION_ENDPOINT'", applications)
        self.assertNotIn("param appConfigurationEndpoint", app_configuration)

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
        self.assertIn(
            "param deployMigrationJob bool = deployApplications", root_template
        )
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

    def test_immutable_image_digest_overrides_mutable_tag(self) -> None:
        root_template = (AZURE_ROOT / "main.bicep").read_text()
        environment_template = (AZURE_ROOT / "environment.bicep").read_text()
        deploy_helper = (AZURE_ROOT / "deploy.sh").read_text()
        self.assertIn("param imageDigest string = ''", root_template)
        self.assertIn("@${imageDigest}", environment_template)
        self.assertIn("empty(imageDigest)", environment_template)
        self.assertIn("GEOVISION_IMAGE_DIGEST", deploy_helper)
        self.assertIn("az acr manifest show-metadata", deploy_helper)

    def test_runtime_only_requires_a_verified_immutable_digest(self) -> None:
        deploy_helper = (AZURE_ROOT / "deploy.sh").read_text()
        runtime_start = deploy_helper.index('if [[ "${mode}" == "runtime" ]]')
        runtime_deploy = deploy_helper.index("deploy_stage runtime true false")
        runtime_guard = deploy_helper[runtime_start:runtime_deploy]
        self.assertIn("--runtime-only requires GEOVISION_IMAGE_DIGEST", runtime_guard)
        self.assertIn('verify_image_digest_in_registry "${acr_name}"', runtime_guard)
        self.assertIn("geovision-backend@${image_digest}", deploy_helper)

    def test_provider_registration_is_an_explicit_bootstrap(self) -> None:
        deploy_helper = (AZURE_ROOT / "deploy.sh").read_text()
        self.assertIn("--register-providers", deploy_helper)
        self.assertIn("AZURE_REGISTER_PROVIDERS:-false", deploy_helper)
        self.assertLess(
            deploy_helper.index('mode}" == "register-providers'),
            deploy_helper.index("GEOVISION_POSTGRES_ADMIN_PASSWORD"),
        )

    def test_release_workflows_use_oidc_and_gate_production(self) -> None:
        workflows = REPO_ROOT / ".github" / "workflows"
        staging = (workflows / "deploy-staging.yml").read_text()
        production = (workflows / "deploy-production.yml").read_text()
        for workflow in (staging, production):
            self.assertIn("azure/login@v2", workflow)
            self.assertIn("id-token: write", workflow)
            self.assertNotIn("AZURE_CLIENT_SECRET", workflow)
        self.assertIn("environment: staging", staging)
        self.assertIn("CI - delivery gates", staging)
        self.assertIn("workflow_dispatch", production)
        self.assertIn("refs/heads/main", production)
        self.assertIn("environment: production", production)
        self.assertIn("staging_image_digest", production)
        self.assertIn("promote-image.sh", production)
        self.assertNotIn("az acr build", production)

    def test_environment_parameter_files_do_not_embed_credentials(self) -> None:
        for name in ("staging.bicepparam", "prod.bicepparam"):
            parameters = (AZURE_ROOT / name).read_text()
            for environment_name in (
                "GEOVISION_POSTGRES_ADMIN_PASSWORD",
                "GEOVISION_SECRET_KEY",
                "GEOVISION_ENCRYPTION_KEY",
            ):
                self.assertIn(
                    f"readEnvironmentVariable('{environment_name}')", parameters
                )
            self.assertNotRegex(
                parameters, r"param (secretKey|encryptionKey) = '[^']+'"
            )


if __name__ == "__main__":
    unittest.main()
