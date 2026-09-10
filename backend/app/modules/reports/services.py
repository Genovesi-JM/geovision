"""Canonical report generation, QA, review, publication, and delivery services."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import uuid
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.time import utc_now
from app.models import (
    Acquisition,
    Asset,
    Dataset,
    DatasetFile,
    Report,
    User,
)
from app.modules.audit.services import record_audit_event
from app.modules.identity.domain import AuthorizationContext
from app.modules.organizations.domain import permission_granted
from app.modules.reports.context_builder import ReportContextBuilder
from app.modules.reports.domain import (
    ReportError,
    ReportQALevel,
    ReportStatus,
    require_report_transition,
)
from app.modules.reports.narrative import DeterministicNarrativeProvider
from app.modules.reports.ports import NarrativeProvider
from app.modules.reports.qa import classify_qa, validate_narrative
from app.modules.reports.renderers import render_report_pdf
from app.modules.reports.schemas import ReportGenerateRequest
from app.modules.economics.schemas import ProviderUsageCreate
from app.modules.economics.services import record_provider_usage
from app.services.event_outbox import enqueue_domain_event
from app.services.storage import StorageService, get_storage_service


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


_UNVERSIONED = {"", "legacy", "legacy-1", "legacy-unversioned", "unknown"}


def _version(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if normalized.lower() in _UNVERSIONED or len(normalized) > 120:
        return None
    return normalized


def _source_version(provenance: Mapping[str, Any]) -> str | None:
    for key in (
        "processor_version",
        "provider_version",
        "adapter_version",
        "algorithm_version",
        "version",
        "schema_version",
    ):
        value = _version(provenance.get(key))
        if value:
            return value
    return None


def _build_provenance(
    *,
    asset: Asset,
    acquisition: Acquisition | None,
    context: Mapping[str, Any],
    context_sha256: str,
    template_version: str,
    narrative_provider: NarrativeProvider,
    narrative_schema_version: str,
) -> dict[str, Any]:
    model_version = _version(getattr(narrative_provider, "model_version", None))
    if model_version is None:
        raise ReportError(
            "narrative_model_version_missing",
            "Narrative output must identify an immutable model version",
        )
    if _version(template_version) is None:
        raise ReportError(
            "template_version_missing",
            "Report generation requires an immutable template version",
        )

    sources: list[dict[str, Any]] = []
    acquisition_context = context.get("acquisition")
    if acquisition is not None and isinstance(acquisition_context, Mapping):
        acquisition_provenance = acquisition_context.get("provenance")
        acquisition_provenance = (
            acquisition_provenance
            if isinstance(acquisition_provenance, Mapping)
            else {}
        )
        is_first_party = (
            (
                not acquisition.provider_code
                or acquisition.provider_code.startswith("geovision")
                or acquisition.legacy_source in {"drone_mission", "asset_inspection"}
            )
            and acquisition.acquisition_type
            in {"DRONE", "IOT", "MANUAL_INSPECTION"}
        )
        provider_version = _source_version(acquisition_provenance)
        sources.append(
            {
                "kind": "mission",
                "id": acquisition.id,
                "provider": (
                    acquisition.provider_code
                    or ("geovision-acquisition" if is_first_party else None)
                ),
                "version": (
                    provider_version
                    or (
                        "geovision-acquisition-v1.0.0"
                        if is_first_party
                        else None
                    )
                ),
                "version_basis": (
                    "provider_or_adapter"
                    if provider_version
                    else ("workflow_schema" if is_first_party else None)
                ),
            }
        )
    for item in context.get("datasets", []):
        if not isinstance(item, Mapping):
            continue
        item_provenance = item.get("provenance")
        item_provenance = item_provenance if isinstance(item_provenance, Mapping) else {}
        sources.append(
            {
                "kind": "dataset",
                "id": item.get("id"),
                "mission_id": item.get("acquisition_id"),
                "provider": item.get("provider"),
                "processor": item_provenance.get("processor"),
                "version": _source_version(item_provenance),
            }
        )
    for item in context.get("kpis", []):
        if not isinstance(item, Mapping):
            continue
        sources.append(
            {
                "kind": "kpi",
                "id": item.get("id"),
                "definition_id": item.get("definition_id"),
                "dataset_id": item.get("dataset_id"),
                "mission_id": item.get("acquisition_id"),
                "provider": item.get("source"),
                "algorithm": item.get("source"),
                "version": _version(item.get("algorithm_version")),
            }
        )
    for item in context.get("observations", []):
        if not isinstance(item, Mapping):
            continue
        sources.append(
            {
                "kind": "observation",
                "id": item.get("id"),
                "dataset_id": item.get("dataset_id"),
                "mission_id": item.get("acquisition_id"),
                "provider": item.get("source"),
                "algorithm": item.get("algorithm"),
                "version": _version(item.get("algorithm_version")),
            }
        )
    for item in context.get("actions", []):
        if not isinstance(item, Mapping):
            continue
        sources.append(
            {
                "kind": "action",
                "id": item.get("id"),
                "observation_id": item.get("source_observation_id"),
                "provider": "geovision-rules",
                "algorithm": item.get("source_rule"),
                "version": _version(item.get("source_rule_version")),
            }
        )
    provenance: dict[str, Any] = {
        "schema_version": "geovision.report-provenance.v1",
        "organization_id": asset.organization_id,
        "workspace_id": asset.workspace_id,
        "asset_id": asset.id,
        "acquisition_id": acquisition.id if acquisition else None,
        "context_schema_version": context.get("schema_version"),
        "context_sha256": context_sha256,
        "template_version": template_version,
        "narrative_provider": narrative_provider.provider_name,
        "narrative_model": narrative_provider.model_name,
        "narrative_model_version": model_version,
        "narrative_schema_version": narrative_schema_version,
        "sources": sources,
    }
    issues = _provenance_issues(provenance)
    provenance["complete"] = not issues
    provenance["issues"] = issues
    return provenance


def _provenance_issues(provenance: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    required = (
        "schema_version",
        "organization_id",
        "asset_id",
        "context_schema_version",
        "context_sha256",
        "template_version",
        "narrative_provider",
        "narrative_model_version",
        "narrative_schema_version",
    )
    for field in required:
        if not str(provenance.get(field) or "").strip():
            issues.append(f"missing:{field}")
    if _version(provenance.get("template_version")) is None:
        issues.append("unversioned:template")
    if _version(provenance.get("narrative_model_version")) is None:
        issues.append("unversioned:narrative_model")
    sources = provenance.get("sources")
    if not isinstance(sources, list) or not sources:
        issues.append("missing:sources")
    else:
        for index, source in enumerate(sources):
            if not isinstance(source, Mapping):
                issues.append(f"invalid:source:{index}")
                continue
            kind = str(source.get("kind") or index)
            if not str(source.get("id") or "").strip():
                issues.append(f"missing:{kind}:id")
            if not str(source.get("provider") or "").strip():
                issues.append(f"missing:{kind}:provider")
            if _version(source.get("version")) is None:
                issues.append(f"missing:{kind}:version")
    return sorted(set(issues))


def _require_publishable_provenance(report: Report) -> dict[str, Any]:
    provenance = _object(report.provenance_json)
    issues = _provenance_issues(provenance)
    if (
        provenance.get("context_sha256") != report.context_sha256
        or provenance.get("template_version") != report.template_version
        or provenance.get("narrative_model_version") != report.narrative_model_version
    ):
        issues.append("mismatch:report")
    if issues:
        raise ReportError(
            "provenance_incomplete",
            "Report provenance is incomplete and must be regenerated before publication",
        )
    return provenance


def _audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    report: Report,
    details: Mapping[str, Any] | None = None,
) -> None:
    record_audit_event(
        db,
        actor=actor,
        action=action,
        resource_type="report",
        resource_id=report.id,
        organization_id=report.organization_id,
        workspace_id=report.workspace_id,
        details={
            "asset_id": report.asset_id,
            "mission_id": report.acquisition_id,
            "revision": report.revision,
            "status": report.status,
            **dict(details or {}),
        },
    )


def _event(
    db: Session,
    *,
    report: Report,
    name: str,
    suffix: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    enqueue_domain_event(
        db,
        name=name,
        aggregate_type="report",
        aggregate_id=report.id,
        idempotency_key=f"report:{report.id}:{suffix}:{report.lifecycle_version}",
        correlation_id=report.acquisition_id or report.asset_id,
        payload={
            "report_id": report.id,
            "organization_id": report.organization_id,
            "workspace_id": report.workspace_id,
            "asset_id": report.asset_id,
            "acquisition_id": report.acquisition_id,
            "report_type": report.report_type,
            "revision": report.revision,
            "status": report.status,
            "qa_level": report.qa_level,
            "output_dataset_id": report.output_dataset_id,
            "output_file_id": report.output_file_id,
            **dict(payload or {}),
        },
    )


def _generation_key(
    *,
    asset: Asset,
    data: ReportGenerateRequest,
    context_sha256: str,
) -> str:
    if data.idempotency_key:
        seed = ":".join(
            (
                "client",
                asset.organization_id,
                asset.id,
                data.report_type,
                data.idempotency_key,
            )
        )
    else:
        seed = ":".join(
            (
                "context",
                asset.organization_id,
                asset.id,
                data.acquisition_id or "none",
                data.report_type,
                data.template_version,
                context_sha256,
            )
        )
    return f"sha256:{hashlib.sha256(seed.encode()).hexdigest()}"


def _default_title(asset: Asset, report_type: str) -> str:
    label = report_type.replace("_", " ").title()
    return f"{asset.name} - {label}"[:240]


def _next_revision(db: Session, asset_id: str, report_type: str) -> int:
    current = (
        db.query(func.max(Report.revision))
        .filter(Report.asset_id == asset_id, Report.report_type == report_type)
        .scalar()
    )
    return int(current or 0) + 1


def _latest_report(db: Session, asset_id: str, report_type: str) -> Report | None:
    return (
        db.query(Report)
        .filter(Report.asset_id == asset_id, Report.report_type == report_type)
        .order_by(Report.revision.desc(), Report.created_at.desc())
        .first()
    )


def _run_narrative(
    *,
    context: Mapping[str, Any],
    evidence_ids: frozenset[str],
    provider: NarrativeProvider,
) -> tuple[dict[str, Any], NarrativeProvider, bool, str | None]:
    try:
        if _version(getattr(provider, "model_version", None)) is None:
            raise ReportError(
                "narrative_model_version_missing",
                "Narrative provider did not identify an immutable model version",
            )
        output = provider.generate(context)
        envelope = validate_narrative(output, evidence_ids=evidence_ids)
        return envelope.model_dump(mode="json"), provider, False, None
    except Exception as exc:
        fallback = DeterministicNarrativeProvider()
        envelope = validate_narrative(
            fallback.generate(context),
            evidence_ids=evidence_ids,
        )
        code = exc.code if isinstance(exc, ReportError) else "provider_unavailable"
        return envelope.model_dump(mode="json"), fallback, True, str(code)


def _write_artifact(
    db: Session,
    *,
    report: Report,
    asset: Asset,
    pdf: bytes,
    storage: StorageService,
    actor: User,
) -> tuple[Dataset, DatasetFile]:
    now = utc_now()
    dataset_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    stem = re.sub(r"[^a-z0-9]+", "-", report.report_type.lower()).strip("-")
    filename = f"{stem}-r{report.revision}.pdf"
    dataset = Dataset(
        id=dataset_id,
        company_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        site_id=(asset.legacy_source_id if asset.legacy_source == "site" else None),
        asset_id=asset.id,
        mission_id=report.acquisition_id,
        name=f"{report.title} (revision {report.revision})",
        description="Canonical GeoVision report artifact",
        source_tool="geovision_reports",
        data_type="report_pdf",
        source="report_engine",
        dataset_type="REPORT_PDF",
        provider_code="geovision_reports",
        source_reference=report.id,
        storage_provider=storage.provider_name,
        object_prefix=None,
        processing_level="REPORT",
        quality_status="PASSED",
        provenance_json=_json(
            {
                "schema_version": "geovision.report-artifact.v1",
                "report_id": report.id,
                "report_revision": report.revision,
                "context_sha256": report.context_sha256,
                "template_version": report.template_version,
                "narrative_model_version": report.narrative_model_version,
                "report_provenance_sha256": hashlib.sha256(
                    report.provenance_json.encode()
                ).hexdigest(),
            }
        ),
        status="ready",
        sector=asset.sector,
        capture_date=now,
        metadata_json=_json(
            {
                "report_id": report.id,
                "report_type": report.report_type,
                "qa_level": report.qa_level,
            }
        ),
        file_count=1,
        total_size_bytes=len(pdf),
        created_at=now,
        updated_at=now,
        processed_at=now,
        created_by_user_id=actor.id,
        lifecycle_version=1,
    )
    file = DatasetFile(
        id=file_id,
        dataset_id=dataset_id,
        filename=filename,
        storage_provider=storage.provider_name,
        object_area="reports",
        file_size=len(pdf),
        mime_type="application/pdf",
        status="pending_upload",
        lifecycle_version=1,
        created_at=now,
    )
    db.add_all((dataset, file))
    db.flush()
    key = storage.generate_dataset_key(
        organization_id=asset.organization_id,
        asset_id=asset.id,
        mission_id=report.acquisition_id,
        dataset_id=dataset.id,
        file_id=file.id,
        area="reports",
        filename=filename,
    )
    uploaded = False
    try:
        stored_key, size, md5_hash, sha256_hash = storage.upload_bytes(
            pdf,
            key,
            content_type="application/pdf",
            metadata={
                "report_id": report.id,
                "organization_id": report.organization_id,
                "asset_id": report.asset_id,
            },
        )
        uploaded = True
        file.storage_key = stored_key
        file.storage_uri = storage.object_uri(stored_key)
        file.file_size = size
        file.md5_hash = md5_hash
        file.sha256_hash = sha256_hash
        file.status = "uploaded"
        file.confirmed_at = now
        dataset.total_size_bytes = size
        dataset.object_prefix = str(Path(stored_key).parent)
        db.flush()
    except Exception:
        if uploaded:
            try:
                storage.delete_file(key)
            except Exception:
                pass
        raise
    return dataset, file


def generate_report(
    db: Session,
    *,
    actor: User,
    asset: Asset,
    data: ReportGenerateRequest,
    context_builder: ReportContextBuilder | None = None,
    narrative_provider: NarrativeProvider | None = None,
    storage: StorageService | None = None,
) -> tuple[Report, bool]:
    acquisition = db.get(Acquisition, data.acquisition_id) if data.acquisition_id else None
    if data.acquisition_id and acquisition is None:
        raise ReportError(
            "acquisition_not_found", "Acquisition was not found for this asset"
        )
    built = (context_builder or ReportContextBuilder()).build(
        db,
        asset=asset,
        acquisition=acquisition,
    )
    generation_key = _generation_key(
        asset=asset,
        data=data,
        context_sha256=built.sha256,
    )
    existing = (
        db.query(Report).filter(Report.generation_key == generation_key).one_or_none()
    )
    if existing is not None:
        if (
            existing.asset_id != asset.id
            or existing.report_type != data.report_type
            or existing.context_sha256 != built.sha256
        ):
            raise ReportError(
                "idempotency_conflict",
                "Idempotency key is already bound to different report evidence",
            )
        return existing, False

    requested_provider = narrative_provider or DeterministicNarrativeProvider()
    narrative, actual_provider, fallback_used, fallback_reason = _run_narrative(
        context=built.context,
        evidence_ids=built.evidence_ids,
        provider=requested_provider,
    )
    qa_level, qa_result = classify_qa(
        built.context,
        narrative_provider=actual_provider.provider_name,
        fallback_used=fallback_used,
    )
    qa_result.update(
        {
            "requested_narrative_provider": requested_provider.provider_name,
            "actual_narrative_provider": actual_provider.provider_name,
            "fallback_reason": fallback_reason,
            "context_sha256": built.sha256,
        }
    )
    provenance = _build_provenance(
        asset=asset,
        acquisition=acquisition,
        context=built.context,
        context_sha256=built.sha256,
        template_version=data.template_version,
        narrative_provider=actual_provider,
        narrative_schema_version=str(narrative["schema_version"]),
    )
    if not provenance["complete"]:
        qa_level = ReportQALevel.HUMAN_REVIEW
        qa_result["level"] = qa_level.value
        qa_result["reasons"] = list(
            dict.fromkeys([*qa_result.get("reasons", []), "incomplete_provenance"])
        )
    qa_result["provenance_complete"] = provenance["complete"]
    qa_result["provenance_issues"] = provenance["issues"]
    now = utc_now()
    previous = _latest_report(db, asset.id, data.report_type)
    auto_approved = qa_level is ReportQALevel.AUTO_APPROVED
    report = Report(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        acquisition_id=acquisition.id if acquisition else None,
        report_type=data.report_type,
        title=(data.title or _default_title(asset, data.report_type)).strip()[:240],
        template_version=data.template_version,
        revision=_next_revision(db, asset.id, data.report_type),
        status=(ReportStatus.APPROVED.value if auto_approved else ReportStatus.DRAFT.value),
        qa_level=qa_level.value,
        context_schema_version=str(built.context["schema_version"]),
        context_json=built.canonical_json,
        context_sha256=built.sha256,
        narrative_provider=actual_provider.provider_name,
        narrative_model=actual_provider.model_name,
        narrative_model_version=provenance["narrative_model_version"],
        narrative_schema_version=str(narrative["schema_version"]),
        narrative_json=_json(narrative),
        provenance_json=_json(provenance),
        qa_result_json=_json(qa_result),
        supersedes_report_id=previous.id if previous else None,
        generation_key=generation_key,
        generated_at=now,
        approved_at=now if auto_approved else None,
        approved_by_user_id=None,
        created_by_user_id=actor.id,
        lifecycle_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(report)
    db.flush()
    record_provider_usage(
        db,
        payload=ProviderUsageCreate(
            organization_id=report.organization_id,
            workspace_id=report.workspace_id,
            report_id=report.id,
            provider=report.narrative_provider,
            service="narrative_generation",
            usage_type="report_narrative",
            quantity=Decimal("1"),
            unit="report",
            occurred_at=now,
            provider_reference=report.context_sha256,
            idempotency_key=(
                f"report:{report.id}:narrative:{report.narrative_model_version}"
            ),
            metadata={
                "model": report.narrative_model,
                "model_version": report.narrative_model_version,
                "fallback_used": fallback_used,
                "context_schema_version": report.context_schema_version,
            },
        ),
        actor=actor,
    )
    pdf = render_report_pdf(
        title=report.title,
        report_type=report.report_type,
        revision=report.revision,
        context=built.context,
        narrative=narrative,
        provenance=provenance,
    )
    dataset, file = _write_artifact(
        db,
        report=report,
        asset=asset,
        pdf=pdf,
        storage=storage or get_storage_service(),
        actor=actor,
    )
    report.output_dataset_id = dataset.id
    report.output_file_id = file.id
    db.flush()
    _audit(
        db,
        actor=actor,
        action="report.generated",
        report=report,
        details={
            "context_sha256": report.context_sha256,
            "narrative_provider": report.narrative_provider,
            "narrative_model_version": report.narrative_model_version,
            "provenance_complete": provenance["complete"],
            "fallback_used": fallback_used,
            "output_dataset_id": dataset.id,
            "output_file_id": file.id,
        },
    )
    _event(
        db,
        report=report,
        name=EventNames.REPORT_GENERATED,
        suffix="generated",
        payload={"context_sha256": report.context_sha256},
    )
    if auto_approved:
        _audit(
            db,
            actor=None,
            action="report.auto_approved",
            report=report,
            details={"qa_level": report.qa_level},
        )
        _event(
            db,
            report=report,
            name=EventNames.REPORT_APPROVED,
            suffix="auto-approved",
        )
    return report, True


def _is_internal(context: AuthorizationContext) -> bool:
    return bool(context.internal_roles)


def authorize_asset(
    *,
    context: AuthorizationContext,
    asset: Asset | None,
    permission: str,
) -> Asset:
    if asset is None or not permission_granted(context.permissions, permission):
        raise ReportError("report_not_found", "Report resource was not found")
    if _is_internal(context):
        return asset
    if (
        not context.active_organization_id
        or not context.active_workspace_id
        or asset.organization_id != context.active_organization_id
        or asset.workspace_id not in {None, context.active_workspace_id}
    ):
        raise ReportError("report_not_found", "Report resource was not found")
    return asset


def get_authorized_report(
    db: Session,
    *,
    context: AuthorizationContext,
    report_id: str,
    permission: str = "report:read",
    include_unpublished: bool = False,
) -> Report:
    report = db.get(Report, report_id)
    if report is None or not permission_granted(context.permissions, permission):
        raise ReportError("report_not_found", "Report was not found")
    if _is_internal(context):
        return report
    if (
        report.organization_id != context.active_organization_id
        or report.workspace_id not in {None, context.active_workspace_id}
        or (not include_unpublished and report.status != ReportStatus.PUBLISHED.value)
    ):
        raise ReportError("report_not_found", "Report was not found")
    return report


def list_authorized_reports(
    db: Session,
    *,
    context: AuthorizationContext,
    asset_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Report]:
    if not permission_granted(context.permissions, "report:read"):
        raise ReportError("report_access_denied", "Report access denied")
    query = db.query(Report)
    if _is_internal(context):
        if context.active_organization_id:
            query = query.filter(Report.organization_id == context.active_organization_id)
    else:
        if not context.active_organization_id or not context.active_workspace_id:
            raise ReportError("report_access_denied", "Report access denied")
        query = query.filter(
            Report.organization_id == context.active_organization_id,
            or_(
                Report.workspace_id == context.active_workspace_id,
                Report.workspace_id.is_(None),
            ),
            Report.status == ReportStatus.PUBLISHED.value,
        )
    if asset_id:
        query = query.filter(Report.asset_id == asset_id)
    if status:
        query = query.filter(Report.status == ReportStatus(status).value)
    return (
        query.order_by(Report.created_at.desc(), Report.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def _check_version(report: Report, expected: int | None) -> None:
    if expected is not None and report.lifecycle_version != expected:
        raise ReportError(
            "version_conflict", "Report changed since it was last read"
        )


def submit_report(
    db: Session,
    *,
    report: Report,
    actor: User,
    expected_version: int | None = None,
    note: str | None = None,
) -> Report:
    _check_version(report, expected_version)
    require_report_transition(report.status, ReportStatus.REVIEW_REQUIRED.value)
    report.status = ReportStatus.REVIEW_REQUIRED.value
    report.lifecycle_version += 1
    report.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="report.review_requested",
        report=report,
        details={"note_present": bool(note)},
    )
    _event(
        db,
        report=report,
        name=EventNames.REPORT_REVIEW_REQUESTED,
        suffix="review-requested",
    )
    return report


def approve_report(
    db: Session,
    *,
    report: Report,
    actor: User,
    context: AuthorizationContext,
    expected_version: int | None = None,
    note: str | None = None,
) -> Report:
    _check_version(report, expected_version)
    if report.qa_level == ReportQALevel.SPECIALIST_REVIEW.value and not permission_granted(
        context.permissions, "analytics:review"
    ):
        raise ReportError(
            "specialist_review_required",
            "A GeoVision specialist must approve this report",
        )
    require_report_transition(report.status, ReportStatus.APPROVED.value)
    now = utc_now()
    report.status = ReportStatus.APPROVED.value
    report.approved_at = now
    report.approved_by_user_id = actor.id
    report.lifecycle_version += 1
    report.updated_at = now
    _audit(
        db,
        actor=actor,
        action="report.approved",
        report=report,
        details={"note_present": bool(note)},
    )
    _event(
        db,
        report=report,
        name=EventNames.REPORT_APPROVED,
        suffix="approved",
    )
    return report


def publish_report(
    db: Session,
    *,
    report: Report,
    actor: User,
    expected_version: int | None = None,
    note: str | None = None,
) -> Report:
    _check_version(report, expected_version)
    _require_publishable_provenance(report)
    require_report_transition(report.status, ReportStatus.PUBLISHED.value)
    now = utc_now()
    prior = (
        db.query(Report)
        .filter(
            Report.asset_id == report.asset_id,
            Report.report_type == report.report_type,
            Report.status == ReportStatus.PUBLISHED.value,
            Report.id != report.id,
        )
        .order_by(Report.revision.desc())
        .all()
    )
    for row in prior:
        require_report_transition(row.status, ReportStatus.SUPERSEDED.value)
        row.status = ReportStatus.SUPERSEDED.value
        row.lifecycle_version += 1
        row.updated_at = now
        _audit(
            db,
            actor=actor,
            action="report.superseded",
            report=row,
            details={"superseded_by_report_id": report.id},
        )
        _event(
            db,
            report=row,
            name=EventNames.REPORT_SUPERSEDED,
            suffix=f"superseded-by-{report.id}",
            payload={"superseded_by_report_id": report.id},
        )
    report.status = ReportStatus.PUBLISHED.value
    report.published_at = now
    report.published_by_user_id = actor.id
    report.lifecycle_version += 1
    report.updated_at = now
    _audit(
        db,
        actor=actor,
        action="report.published",
        report=report,
        details={"note_present": bool(note), "superseded_count": len(prior)},
    )
    _event(
        db,
        report=report,
        name=EventNames.REPORT_PUBLISHED,
        suffix="published",
        payload={"superseded_report_ids": [row.id for row in prior]},
    )
    return report


def report_payload(report: Report, *, detail: bool = False) -> dict[str, Any]:
    payload = {
        "id": report.id,
        "organization_id": report.organization_id,
        "workspace_id": report.workspace_id,
        "asset_id": report.asset_id,
        "acquisition_id": report.acquisition_id,
        "report_type": report.report_type,
        "title": report.title,
        "template_version": report.template_version,
        "revision": report.revision,
        "status": report.status,
        "qa_level": report.qa_level,
        "context_schema_version": report.context_schema_version,
        "context_sha256": report.context_sha256,
        "narrative_provider": report.narrative_provider,
        "narrative_model": report.narrative_model,
        "narrative_model_version": report.narrative_model_version,
        "narrative_schema_version": report.narrative_schema_version,
        "provenance": _object(report.provenance_json),
        "qa_result": _object(report.qa_result_json),
        "output_dataset_id": report.output_dataset_id,
        "output_file_id": report.output_file_id,
        "supersedes_report_id": report.supersedes_report_id,
        "generated_at": report.generated_at,
        "approved_at": report.approved_at,
        "published_at": report.published_at,
        "lifecycle_version": report.lifecycle_version,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }
    if detail:
        payload.update(
            {
                "context": _object(report.context_json),
                "narrative": _object(report.narrative_json),
            }
        )
    return payload


def download_report(
    db: Session,
    *,
    report: Report,
    storage: StorageService | None = None,
) -> tuple[bytes, str]:
    file = db.get(DatasetFile, report.output_file_id) if report.output_file_id else None
    if (
        file is None
        or file.status != "uploaded"
        or file.deleted_at is not None
        or not file.storage_key
        or file.mime_type != "application/pdf"
    ):
        raise ReportError("report_artifact_missing", "Report artifact is unavailable")
    data = (storage or get_storage_service()).download_file(file.storage_key)
    if not data.startswith(b"%PDF-"):
        raise ReportError("report_artifact_invalid", "Report artifact is invalid")
    return data, file.filename


def record_report_download(db: Session, *, report: Report, actor: User) -> None:
    _audit(
        db,
        actor=actor,
        action="report.downloaded",
        report=report,
        details={"output_file_id": report.output_file_id},
    )


__all__ = [
    "approve_report",
    "authorize_asset",
    "download_report",
    "generate_report",
    "get_authorized_report",
    "list_authorized_reports",
    "publish_report",
    "record_report_download",
    "report_payload",
    "submit_report",
]
