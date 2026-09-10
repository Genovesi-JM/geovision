from __future__ import annotations

from io import BytesIO
import base64
import json
from pathlib import Path
import uuid
from zipfile import ZipFile

import httpx
import pytest

from app.core.config import Settings
from app.core.event_names import EventNames
from app.core.integration import IntegrationResult
from app.core.time import utc_now
from app.integrations.processing.fake import DeterministicProcessingProvider
from app.integrations.processing.nodeodm import NodeODMProcessingProvider
from app.integrations.storage.local import LocalObjectStorageProvider
from app.models import (
    Account,
    Asset,
    Company,
    Dataset,
    DatasetFile,
    EventConsumerReceipt,
    EventDeliveryAttempt,
    EventOutbox,
    ProcessingJob,
    ProcessingJobOutput,
    User,
)
from app.modules.processing.ports import ProviderArtifact
from app.modules.processing.schemas import ProcessingJobCreate
from app.modules.processing.services import (
    create_processing_job,
    processing_job_out,
    retry_processing_job,
    run_processing_cycle,
)
from app.services.event_consumers import default_event_consumers
from app.services.event_outbox import dispatch_pending_events, enqueue_domain_event
from app.services.storage import StorageService


def _config(**values) -> Settings:
    return Settings(
        _env_file=None,
        processing_provider="fake",
        processing_worker_poll_seconds=0.01,
        processing_retry_initial_seconds=0,
        processing_retry_max_seconds=0,
        **values,
    )


def _source_dataset(db, tmp_path: Path, *, image_count: int = 2):
    suffix = uuid.uuid4().hex
    actor = db.query(User).filter(User.email == "teste@admin.com").one()
    organization = Company(
        name=f"Processing {suffix[:8]}",
        email=f"processing-{suffix}@example.com",
        status="active",
    )
    db.add(organization)
    db.flush()
    workspace = Account(
        organization_id=organization.id,
        name="Processing workspace",
        sector_focus="agriculture",
        entity_type="company",
        customer_type="business",
        dashboard_profile="business",
        use_cases="[]",
        modules_enabled="[]",
    )
    db.add(workspace)
    db.flush()
    asset = Asset(
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FARM",
        name="Processing field",
        status="active",
        metadata_json="{}",
    )
    db.add(asset)
    db.flush()
    dataset = Dataset(
        company_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        name="RGB flight capture",
        source_tool="geovision_capture",
        data_type="rgb_images",
        dataset_type="RGB_IMAGES",
        provider_code="geovision_capture",
        storage_provider="local",
        processing_level="RAW",
        quality_status="PASSED",
        provenance_json="{}",
        metadata_json="{}",
        status="ready",
        sector="AGRICULTURE",
        file_count=image_count,
        lifecycle_version=1,
    )
    db.add(dataset)
    db.flush()
    storage = StorageService(
        LocalObjectStorageProvider(
            root=tmp_path / suffix / "objects",
            public_base_url="http://testserver",
            signing_secret="processing-test-signing-secret",
        )
    )
    total_size = 0
    for index in range(image_count):
        content = b"\xff\xd8\xffGEOVISION-IMAGE-" + str(index).encode()
        key = f"processing-input/{dataset.id}/{index}.jpg"
        stored_key, size, md5_hash, sha256_hash = storage.upload_bytes(
            content, key, "image/jpeg"
        )
        total_size += size
        db.add(
            DatasetFile(
                dataset_id=dataset.id,
                filename=f"capture-{index}.jpg",
                storage_key=stored_key,
                storage_provider="local",
                storage_uri=storage.object_uri(stored_key),
                object_area="raw",
                file_size=size,
                mime_type="image/jpeg",
                md5_hash=md5_hash,
                sha256_hash=sha256_hash,
                status="uploaded",
                confirmed_at=utc_now(),
            )
        )
    dataset.total_size_bytes = total_size
    db.commit()
    return actor, dataset, storage


def _run_to_provider_completion(db, job: ProcessingJob, storage, provider, config):
    resolver = lambda _: provider
    submitted = run_processing_cycle(
        db,
        worker_id="processing-test-worker",
        provider_resolver=resolver,
        storage=storage,
        config=config,
    )
    assert submitted["submitted"] == 1
    db.refresh(job)
    job.next_poll_at = utc_now()
    db.commit()
    return run_processing_cycle(
        db,
        worker_id="processing-test-worker",
        provider_resolver=resolver,
        storage=storage,
        config=config,
    )


def test_deterministic_processing_registers_normal_datasets_and_events(
    db_session, tmp_path
):
    actor, source, storage = _source_dataset(db_session, tmp_path)
    config = _config()
    job = create_processing_job(
        db_session,
        actor=actor,
        config=config,
        data=ProcessingJobCreate(
            source_dataset_ids=[source.id],
            requested_outputs=["ORTHOMOSAIC", "DSM", "POINT_CLOUD"],
            provider="fake",
            estimated_cost_amount=0,
            idempotency_key=f"processing-test-{uuid.uuid4().hex}",
        ),
    )
    db_session.commit()

    completed = _run_to_provider_completion(
        db_session,
        job,
        storage,
        DeterministicProcessingProvider(),
        config,
    )
    assert completed["completed"] == 1
    db_session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.progress_percent == 100
    assert job.processor_version == "1"
    payload = processing_job_out(job)
    assert {item["output_type"] for item in payload["generated_outputs"]} == {
        "ORTHOMOSAIC",
        "DSM",
        "POINT_CLOUD",
    }
    generated = (
        db_session.query(Dataset)
        .join(ProcessingJobOutput, ProcessingJobOutput.dataset_id == Dataset.id)
        .filter(ProcessingJobOutput.processing_job_id == job.id)
        .all()
    )
    assert {row.dataset_type for row in generated} == {
        "ORTHOMOSAIC",
        "DSM",
        "POINT_CLOUD",
    }
    for dataset in generated:
        assert dataset.status == "ready"
        assert dataset.quality_status == "PASSED"
        assert dataset.storage_provider == "local"
        provenance = json.loads(dataset.provenance_json)
        assert provenance["processing_job_id"] == job.id
        assert provenance["source_dataset_ids"] == [source.id]
        assert dataset.files[0].status == "uploaded"
        assert storage.download_file(dataset.files[0].storage_key)
    event_names = {
        row.event_type
        for row in db_session.query(EventOutbox)
        .filter(EventOutbox.aggregate_id.in_([job.id, *[row.id for row in generated]]))
        .all()
    }
    assert {
        EventNames.PROCESSING_REQUESTED,
        EventNames.PROCESSING_COMPLETED,
        EventNames.DATASET_CREATED,
        EventNames.DATASET_READY,
    }.issubset(event_names)
    assert (
        run_processing_cycle(
            db_session,
            worker_id="processing-test-worker",
            provider_resolver=lambda _: DeterministicProcessingProvider(),
            storage=storage,
            config=config,
        )["claimed"]
        == 0
    )


class _MissingOutputProvider(DeterministicProcessingProvider):
    def retrieve_outputs(self, external_reference: str):
        del external_reference
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="retrieve_outputs",
            value=(
                ProviderArtifact(
                    "odm_orthophoto/odm_orthophoto.tif",
                    b"II*\x00ONLY-ORTHOMOSAIC",
                    "image/tiff",
                ),
            ),
        )


def test_missing_output_requires_review_and_operator_retry_is_recoverable(
    db_session, tmp_path
):
    actor, source, storage = _source_dataset(db_session, tmp_path)
    config = _config()
    job = create_processing_job(
        db_session,
        actor=actor,
        config=config,
        data=ProcessingJobCreate(
            source_dataset_ids=[source.id],
            requested_outputs=["ORTHOMOSAIC", "DSM"],
            provider="fake",
            idempotency_key=f"processing-review-{uuid.uuid4().hex}",
        ),
    )
    db_session.commit()
    outcome = _run_to_provider_completion(
        db_session, job, storage, _MissingOutputProvider(), config
    )
    assert outcome["needs_review"] == 1
    db_session.refresh(job)
    assert job.status == "NEEDS_REVIEW"
    assert json.loads(job.quality_report_json)["missing_outputs"] == ["DSM"]
    previous_version = job.lifecycle_version
    retry_processing_job(
        db_session,
        job=job,
        actor=actor,
        expected_version=previous_version,
        provider_code="nodeodm",
    )
    db_session.commit()
    assert job.status == "REQUESTED"
    assert job.lifecycle_version == previous_version + 1
    assert job.error_code is None
    assert job.provider_code == "nodeodm"


def test_dataset_ready_event_creates_one_automatic_job(db_session, tmp_path):
    _, source, _ = _source_dataset(db_session, tmp_path)
    db_session.query(EventDeliveryAttempt).delete()
    db_session.query(EventConsumerReceipt).delete()
    db_session.query(EventOutbox).delete()
    db_session.commit()
    config = _config(
        processing_auto_create_enabled=True,
        processing_default_outputs="ORTHOMOSAIC,DSM",
        queue_provider="database",
        event_retry_initial_seconds=0,
        event_retry_max_seconds=0,
    )
    enqueue_domain_event(
        db_session,
        name=EventNames.DATASET_READY,
        aggregate_type="dataset",
        aggregate_id=source.id,
        idempotency_key=f"automatic-ready-{source.id}",
        payload={"dataset_id": source.id},
    )
    db_session.commit()
    dispatched = dispatch_pending_events(
        db_session,
        worker_id="automatic-processing-consumer",
        registry=default_event_consumers(config),
        config=config,
    )
    assert dispatched["published"] == 1
    jobs = (
        db_session.query(ProcessingJob)
        .filter(ProcessingJob.idempotency_key.like(f"processing:auto:{source.id}:%"))
        .all()
    )
    assert len(jobs) == 1
    assert json.loads(jobs[0].requested_outputs_json) == ["ORTHOMOSAIC", "DSM"]


def test_processing_api_is_internal_and_status_is_visible(client, db_session, tmp_path):
    _, source, _ = _source_dataset(db_session, tmp_path)
    admin_login = client.post(
        "/auth/login", json={"email": "teste@admin.com", "password": "123456"}
    )
    customer_login = client.post(
        "/auth/login", json={"email": "teste@clientes.com", "password": "123456"}
    )
    admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    customer = {"Authorization": f"Bearer {customer_login.json()['access_token']}"}
    response = client.post(
        "/processing/jobs",
        headers=admin,
        json={
            "source_dataset_ids": [source.id],
            "requested_outputs": ["ORTHOMOSAIC"],
            "provider": "fake",
            "idempotency_key": f"processing-api-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "REQUESTED"
    job_id = response.json()["id"]
    visible = client.get(f"/processing/jobs/{job_id}", headers=admin)
    assert visible.status_code == 200
    assert visible.json()["source_dataset_ids"] == [source.id]
    assert client.get(f"/processing/jobs/{job_id}", headers=customer).status_code == 403


def _nodeodm_archive() -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("odm_orthophoto/odm_orthophoto.tif", b"II*\x00ORTHO")
        archive.writestr("odm_dem/dsm.tif", b"II*\x00DSM")
        archive.writestr(
            "odm_georeferencing/odm_georeferenced_model.laz", b"LASFPOINTS"
        )
        archive.writestr("../ignored.tif", b"unsafe")
    return stream.getvalue()


def test_nodeodm_adapter_submits_polls_cancels_and_normalizes_without_sdk():
    archive = _nodeodm_archive()
    seen_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/info":
            return httpx.Response(
                200,
                json={"engine": "odm", "engineVersion": "3.5", "version": "2"},
            )
        if request.url.path == "/task/new":
            seen_headers.append(request.headers["set-uuid"])
            return httpx.Response(200, json={"uuid": request.headers["set-uuid"]})
        if request.url.path.endswith("/info"):
            return httpx.Response(
                200,
                json={"status": {"code": 40}, "progress": 100},
            )
        if request.url.path.endswith("/download/all.zip"):
            return httpx.Response(200, content=archive)
        if request.url.path == "/task/cancel":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404)

    config = Settings(
        _env_file=None,
        processing_provider="nodeodm",
        nodeodm_base_url="http://nodeodm.test:3000",
        nodeodm_token="nodeodm-test-token",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = NodeODMProcessingProvider(config, client=client)
    request = ProcessingJobCreate(
        source_dataset_ids=[str(uuid.uuid4())],
        requested_outputs=["ORTHOMOSAIC", "DSM", "POINT_CLOUD"],
    )
    from app.modules.processing.ports import ProcessingInput, ProcessingRequest

    submission = provider.submit(
        ProcessingRequest(
            job_id=str(uuid.uuid4()),
            name="NodeODM contract",
            inputs=(
                ProcessingInput("one.jpg", b"one", "image/jpeg"),
                ProcessingInput("two.jpg", b"two", "image/jpeg"),
            ),
            requested_outputs=tuple(request.requested_outputs),
            options={"dsm": True},
        ),
        idempotency_key="stable-nodeodm-contract",
    )
    assert submission.ok and submission.value is not None
    assert submission.value.processor_name == "odm"
    assert submission.value.processor_version == "3.5"
    assert len(seen_headers) == 1
    assert provider.status(submission.value.external_reference).value.state == "COMPLETED"
    raw = provider.retrieve_outputs(submission.value.external_reference)
    assert raw.ok and raw.value is not None
    normalized = provider.normalize_outputs(
        raw.value,
        requested_outputs=("ORTHOMOSAIC", "DSM", "POINT_CLOUD"),
    )
    assert normalized.ok and normalized.value is not None
    assert {item.dataset_type for item in normalized.value} == {
        "ORTHOMOSAIC",
        "DSM",
        "POINT_CLOUD",
    }
    assert provider.cancel(submission.value.external_reference).ok
    assert "nodeodm-test-token" not in repr(submission)
    client.close()


def test_processing_configuration_fails_closed_and_redacts_nodeodm_token():
    config = Settings(
        _env_file=None,
        processing_provider="nodeodm",
        nodeodm_base_url="http://127.0.0.1:3000",
        nodeodm_token="sensitive-nodeodm-token",
    )
    assert config.model_dump()["nodeodm_token"] == "[REDACTED]"
    production_values = {
        "_env_file": None,
        "env": "prod",
        "secret_key": "processing-production-secret-key-000001",
        "encryption_key": base64.urlsafe_b64encode(b"p" * 32).decode(),
        "frontend_base": "https://geovision.example",
        "backend_base": "https://api.geovision.example",
    }
    with pytest.raises(ValueError, match="NODEODM_BASE_URL"):
        Settings(
            **production_values,
            processing_provider="nodeodm",
            nodeodm_base_url="http://nodeodm.internal:3000",
        )
    with pytest.raises(ValueError, match="automatic processing"):
        Settings(
            **production_values,
            processing_provider="fake",
            processing_auto_create_enabled=True,
        )
