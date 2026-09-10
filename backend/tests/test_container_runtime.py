from pathlib import Path

import yaml

from app.core.config import Settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"


def test_backend_image_is_non_root_and_self_health_checking():
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim AS runtime" in dockerfile
    assert "COPY --chown=10001:10001 . ." in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "'/health'" in dockerfile
    assert 'CMD ["python", "start.py", "serve"]' in dockerfile

    deployment_requirements = (
        BACKEND_ROOT / "requirements.deploy.txt"
    ).read_text(encoding="utf-8")
    assert "azure-servicebus>=7.14.3,<8.0.0" in deployment_requirements
    assert "azure-monitor-opentelemetry>=1.8.10,<1.9.0" in deployment_requirements


def test_local_api_and_workers_share_the_canonical_image_contract():
    compose_files = (
        REPOSITORY_ROOT / "docker-compose.yml",
        REPOSITORY_ROOT / "docker-compose.processing.yml",
        REPOSITORY_ROOT / "docker-compose.intelligence.yml",
    )

    combined = "\n".join(path.read_text(encoding="utf-8") for path in compose_files)
    assert "Dockerfile.iot" not in combined
    assert combined.count("dockerfile: Dockerfile") == 7
    # A shared API image has an HTTP healthcheck; non-HTTP worker processes
    # must explicitly disable that inherited check in local Compose.
    assert combined.count("disable: true") == 6

    for path in compose_files:
        services = yaml.safe_load(path.read_text(encoding="utf-8"))["services"]
        for name, service in services.items():
            if not name.endswith("worker"):
                continue
            assert service["build"]["dockerfile"] == "Dockerfile"
            assert service["healthcheck"]["disable"] is True
            assert service["depends_on"]["backend"]["condition"] == "service_healthy"


def test_deployment_startup_controls_bind_from_environment(monkeypatch):
    monkeypatch.setenv("RUN_MIGRATIONS_ON_STARTUP", "false")
    monkeypatch.setenv("STARTUP_COMPATIBILITY_BOOTSTRAP", "false")
    monkeypatch.setenv("READINESS_REQUIRE_CURRENT_SCHEMA", "true")

    config = Settings(_env_file=None)

    assert config.run_migrations_on_startup is False
    assert config.startup_compatibility_bootstrap is False
    assert config.readiness_require_current_schema is True
