"""Standalone, dotenv-free report tests using synthetic SQLite only."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from pydantic_settings import BaseSettings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_settings_init = BaseSettings.__init__


def _no_dotenv(self, *args, **kwargs):
    kwargs["_env_file"] = None
    return _settings_init(self, *args, **kwargs)


with patch.dict(os.environ, {
    "ENV": "test", "DATABASE_URL": "sqlite://", "ACCOUNTS_DATABASE_URL": "sqlite://",
    "SECRET_KEY": "synthetic-report-tests-only-0123456789abcdef",
    "RUN_MIGRATIONS_ON_STARTUP": "false", "STARTUP_COMPATIBILITY_BOOTSTRAP": "false",
}, clear=True), patch.object(BaseSettings, "__init__", _no_dotenv):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.core.database import Base
    from app.models import Account, Asset, Company, Dataset, KpiDefinition, KpiValue, Observation, User
    from app.integrations.storage.local import LocalObjectStorageProvider
    from app.modules.reports.context_builder import ReportContextBuilder
    from app.modules.reports.domain import SYNTHETIC_REPORT_NOTICE, has_synthetic_marker, report_contains_synthetic
    from app.modules.reports.narrative import DeterministicNarrativeProvider
    from app.modules.reports.qa import classify_qa, validate_narrative
    from app.modules.reports.schemas import ReportGenerateRequest
    from app.modules.reports.services import download_report, generate_report
    from app.services.storage import StorageService


class SyntheticReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool)

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.temporary = tempfile.TemporaryDirectory(prefix="geovision-synthetic-report-")
        self.path = Path(self.temporary.name)
        self.storage = StorageService(LocalObjectStorageProvider(root=self.path / "objects", public_base_url="http://testserver", signing_secret="synthetic-report-storage-signing-only"))
        self.actor = User(email="report-pilot@example.com", role="admin", is_active=True)
        self.organization = Company(name="Piloto Espana", email="pilot@example.com", country="Spain", status="active")
        self.db.add_all([self.actor, self.organization])
        self.db.flush()
        self.workspace = Account(organization_id=self.organization.id, name="Piloto Espana", sector_focus="agriculture", customer_type="business", entity_type="org", dashboard_profile="business")
        self.db.add(self.workspace)
        self.db.flush()
        self.asset = Asset(organization_id=self.organization.id, workspace_id=self.workspace.id, sector="AGRICULTURE", asset_type="FIELD", name="Piloto Espana - parcela", location_label="Espana - ubicacion ficticia", status="active", metadata_json="{}", created_by_user_id=self.actor.id, updated_by_user_id=self.actor.id)
        self.db.add(self.asset)
        self.db.flush()
        self.dataset = Dataset(company_id=self.organization.id, workspace_id=self.workspace.id, asset_id=self.asset.id, name="Piloto - datos de prueba", dataset_type="NDVI", provider_code="pilot_fixture", storage_provider="local", processing_level="DERIVED", quality_status="PASSED", status="ready", sector="AGRICULTURE", capture_date=datetime(2026, 9, 12, 12), metadata_json="{}", provenance_json=json.dumps({"processor_version": "1.0.0"}))
        self.definition = KpiDefinition(sector="AGRICULTURE", key="pilot_ndvi", label="Mean NDVI", name="Mean NDVI", unit="index", calculator="agriculture.ndvi_mean", calculator_version="1.0.0", importance="PRIMARY", display_format_json="{}", status_policy_json="{}", is_active=True)
        self.db.add_all([self.dataset, self.definition])
        self.db.flush()
        self.kpi = KpiValue(kpi_definition_id=self.definition.id, account_id=self.workspace.id, organization_id=self.organization.id, workspace_id=self.workspace.id, asset_id=self.asset.id, dataset_id=self.dataset.id, value="0.6375", numeric_value=0.6375, status="GOOD", confidence=0.9, measured_at=datetime(2026, 9, 12, 12), source="drone:ndvi", algorithm_version="1.0.0", provenance_json="{}")
        self.observation = Observation(organization_id=self.organization.id, workspace_id=self.workspace.id, asset_id=self.asset.id, dataset_id=self.dataset.id, observation_type="PILOT_FINDING", severity="INFO", confidence=0.9, source="drone:ndvi", algorithm_key="pilot.example", algorithm_version="1.0.0", validation_status="VALIDATED", metadata_json="{}", provenance_json="{}", detected_at=datetime(2026, 9, 12, 12))
        self.db.add_all([self.kpi, self.observation])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temporary.cleanup()

    def context(self):
        self.db.flush()
        return ReportContextBuilder().build(self.db, asset=self.asset)

    def test_explicit_synthetic_markers(self):
        for value in [{"synthetic": True}, {"data_mode": "synthetic"}, {"demo_seed": {"synthetic": True}}, {"agriculture_analysis": {"synthetic": True}}, {"data_classification": {"synthetic": True}}]:
            with self.subTest(value=value):
                self.assertTrue(has_synthetic_marker(value))

    def test_marker_does_not_guess(self):
        for value in [{}, None, {"synthetic": "false"}, {"synthetic": "true"}, {"synthetic": 1}, {"synthetic": False}, {"name": "SYNTHETIC demo"}, {"demo_seed": {"synthetic": "true"}}]:
            with self.subTest(value=value):
                self.assertFalse(has_synthetic_marker(value))

    def test_real_context_and_narrative_unchanged(self):
        built = self.context()
        self.assertNotIn("data_classification", built.context)
        narrative = DeterministicNarrativeProvider().generate(built.context)
        self.assertIn("validated asset intelligence", narrative["executive_summary"])
        self.assertNotIn(SYNTHETIC_REPORT_NOTICE, built.canonical_json)

    def assert_classified(self, origin):
        built = self.context()
        self.assertTrue(report_contains_synthetic(built.context))
        classification = built.context["data_classification"]
        self.assertEqual(classification["mode"], "synthetic" if origin == "asset" else "contains_synthetic")
        self.assertEqual(classification["notice"], SYNTHETIC_REPORT_NOTICE)
        self.assertEqual(built.context["limitations"][0], SYNTHETIC_REPORT_NOTICE)
        self.assertEqual(hashlib.sha256(built.canonical_json.encode()).hexdigest(), built.sha256)
        if origin.startswith("dataset"):
            self.assertEqual(classification["synthetic_dataset_ids"], [self.dataset.id])
            self.assertTrue(built.context["datasets"][0]["synthetic"])
        narrative = DeterministicNarrativeProvider().generate(built.context)
        self.assertEqual(narrative["executive_summary"], SYNTHETIC_REPORT_NOTICE)
        self.assertNotIn("Measured facts", json.dumps(narrative))
        validate_narrative(narrative, evidence_ids=built.evidence_ids)
        level, result = classify_qa(built.context, narrative_provider="deterministic", fallback_used=False)
        self.assertEqual(level.value, "HUMAN_REVIEW")
        self.assertIn("synthetic_demonstration_requires_review", result["reasons"])

    def test_asset_marker(self):
        self.asset.metadata_json = json.dumps({"synthetic": True})
        self.assert_classified("asset")

    def test_dataset_metadata_marker(self):
        self.dataset.metadata_json = json.dumps({"agriculture_analysis": {"synthetic": True}})
        self.assert_classified("dataset_metadata")

    def test_dataset_provenance_marker(self):
        self.dataset.provenance_json = json.dumps({"synthetic": True, "processor_version": "1.0.0"})
        self.assert_classified("dataset_provenance")

    def test_kpi_marker(self):
        self.kpi.provenance_json = json.dumps({"synthetic": True})
        self.assert_classified("kpi")

    def test_observation_marker(self):
        self.observation.metadata_json = json.dumps({"synthetic": True})
        self.assert_classified("observation")

    def test_mixed_critical_report_keeps_specialist_review(self):
        self.dataset.metadata_json = json.dumps({"synthetic": True})
        self.observation.severity = "CRITICAL"
        built = self.context()
        level, result = classify_qa(built.context, narrative_provider="deterministic", fallback_used=False)
        self.assertEqual(level.value, "SPECIALIST_REVIEW")
        self.assertIn("synthetic_demonstration_requires_review", result["reasons"])

    def test_real_report_still_uses_configured_narrative(self):
        class ConfiguredNarrative(DeterministicNarrativeProvider):
            provider_name = "configured-test-provider"
            model_version = "configured-test-v1.0.0"
            calls = 0

            def generate(self, context):
                self.calls += 1
                return super().generate(context)

        provider = ConfiguredNarrative()
        report, _ = generate_report(self.db, actor=self.actor, asset=self.asset, data=ReportGenerateRequest(), narrative_provider=provider, storage=self.storage)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(report.narrative_provider, provider.provider_name)
        self.assertNotIn("data_classification", json.loads(report.provenance_json))
        pdf, _ = download_report(self.db, report=report, storage=self.storage)
        self.assertNotIn(b"SYNTHETIC DEMONSTRATION", pdf)

    def test_unused_dataset_does_not_mark_selected_evidence(self):
        other = Dataset(company_id=self.organization.id, workspace_id=self.workspace.id, asset_id=self.asset.id, name="Unused synthetic input", dataset_type="NDVI", status="ready", metadata_json=json.dumps({"synthetic": True}))
        self.db.add(other)
        self.assertFalse(report_contains_synthetic(self.context().context))

    def test_generation_skips_external_provider_and_labels_pdf_every_page(self):
        self.asset.metadata_json = json.dumps({"synthetic": True})
        self.dataset.metadata_json = json.dumps({"synthetic": True})

        class ExternalMustNotRun:
            provider_name = "external"
            model_name = "not-configured"
            model_version = "1.0.0"
            calls = 0

            def generate(self, context):
                self.calls += 1
                raise AssertionError("Synthetic data must not be sent to an external provider")

        provider = ExternalMustNotRun()
        report, created = generate_report(self.db, actor=self.actor, asset=self.asset, data=ReportGenerateRequest(title="Piloto Espana - demostracion sintetica"), narrative_provider=provider, storage=self.storage)
        self.assertEqual(provider.calls, 0)
        self.assertTrue(created)
        self.assertEqual(report.status, "DRAFT")
        self.assertEqual(report.qa_level, "HUMAN_REVIEW")
        self.assertEqual(report.narrative_provider, "deterministic")
        self.assertEqual(report.narrative_model_version, "geovision-synthetic-v1.0.0")
        self.assertTrue(json.loads(report.provenance_json)["data_classification"]["synthetic"])
        self.assertTrue(json.loads(report.qa_result_json)["external_narrative_skipped"])
        self.assertEqual(json.loads(report.narrative_json)["executive_summary"], SYNTHETIC_REPORT_NOTICE)
        pdf, _ = download_report(self.db, report=report, storage=self.storage)
        for value in [b"SYNTHETIC DEMONSTRATION ONLY", b"Demonstration indicators"]:
            self.assertIn(value, pdf)
        for value in [b"Validated indicators", b"Measured facts", b"Measured at"]:
            self.assertNotIn(value, pdf)
        page_count = len(re.findall(rb"/Type /Page\b", pdf))
        self.assertGreaterEqual(page_count, 2)
        self.assertEqual(pdf.count(b"SYNTHETIC DEMONSTRATION - NOT REAL MEASUREMENTS"), page_count)
        output = os.environ.get("GEOVISION_SYNTHETIC_REPORT_QA_PATH")
        if output:
            Path(output).write_bytes(pdf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
