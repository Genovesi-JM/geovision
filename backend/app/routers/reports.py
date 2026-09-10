"""HTTP transport for canonical report generation and publication."""

from __future__ import annotations

from io import BytesIO
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_authorization_context, get_current_user
from app.integrations.narrative import create_narrative_provider
from app.integrations.registry import get_feature_flag_evaluator
from app.integrations.registry.sector_rollout import sector_rollout_enabled
from app.models import Asset, User
from app.modules.identity.domain import AuthorizationContext
from app.modules.reports.domain import ReportError, ReportStatus
from app.modules.reports.schemas import (
    ReportDecisionRequest,
    ReportDetailOut,
    ReportGenerateRequest,
    ReportListOut,
    ReportOut,
)
from app.modules.reports.services import (
    approve_report,
    authorize_asset,
    download_report,
    generate_report,
    get_authorized_report,
    list_authorized_reports,
    publish_report,
    record_report_download,
    report_payload,
    submit_report,
)


router = APIRouter(tags=["reports"])

_ROLLOUT_SECTORS = {
    "AGRICULTURE",
    "ENVIRONMENTAL",
    "INFRASTRUCTURE",
    "MINING",
    "PORTS_INDUSTRIAL",
}


def _http_error(exc: ReportError) -> HTTPException:
    if exc.code in {"report_not_found", "acquisition_not_found"}:
        code = 404
    elif exc.code in {
        "report_access_denied",
        "sector_rollout_disabled",
        "specialist_review_required",
    }:
        code = 403
    elif exc.code in {"version_conflict", "idempotency_conflict", "invalid_transition"}:
        code = 409
    elif exc.code in {"report_artifact_missing", "report_artifact_invalid"}:
        code = 503
    else:
        code = 400
    return HTTPException(status_code=code, detail=str(exc))


@router.post(
    "/assets/{asset_id}/reports",
    response_model=ReportDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_asset_report(
    asset_id: str,
    payload: ReportGenerateRequest,
    response: Response,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        asset = authorize_asset(
            context=context,
            asset=db.get(Asset, asset_id),
            permission="report:generate",
        )
        if asset.sector in _ROLLOUT_SECTORS and not sector_rollout_enabled(
            db,
            context=context,
            sector=asset.sector,
            evaluator=get_feature_flag_evaluator(),
        ):
            raise ReportError(
                "sector_rollout_disabled",
                "Sector report generation is disabled for this workspace member",
            )
        report, created = generate_report(
            db,
            actor=user,
            asset=asset,
            data=payload,
            narrative_provider=create_narrative_provider(),
        )
        db.commit()
        db.refresh(report)
        if not created:
            response.status_code = status.HTTP_200_OK
        response.headers["Idempotency-Replayed"] = "false" if created else "true"
        return report_payload(report, detail=True)
    except ReportError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503, detail="Report generation is unavailable"
        ) from exc


@router.get("/reports", response_model=ReportListOut)
def list_reports(
    asset_id: str | None = None,
    report_status: ReportStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        rows = list_authorized_reports(
            db,
            context=context,
            asset_id=asset_id,
            status=report_status.value if report_status else None,
            limit=limit,
            offset=offset,
        )
        return {"items": [report_payload(row) for row in rows], "total": len(rows)}
    except (ReportError, ValueError) as exc:
        raise _http_error(
            exc
            if isinstance(exc, ReportError)
            else ReportError("invalid_status", str(exc))
        ) from exc


@router.get("/reports/{report_id}", response_model=ReportDetailOut)
def get_report_detail(
    report_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        report = get_authorized_report(db, context=context, report_id=report_id)
        return report_payload(report, detail=True)
    except ReportError as exc:
        raise _http_error(exc) from exc


@router.post("/reports/{report_id}/submit", response_model=ReportOut)
def submit_report_for_review(
    report_id: str,
    payload: ReportDecisionRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        report = get_authorized_report(
            db,
            context=context,
            report_id=report_id,
            permission="report:generate",
            include_unpublished=True,
        )
        submit_report(
            db,
            report=report,
            actor=user,
            expected_version=payload.expected_lifecycle_version,
            note=payload.note,
        )
        db.commit()
        db.refresh(report)
        return report_payload(report)
    except ReportError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/reports/{report_id}/approve", response_model=ReportOut)
def approve_report_review(
    report_id: str,
    payload: ReportDecisionRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        report = get_authorized_report(
            db,
            context=context,
            report_id=report_id,
            permission="report:review",
            include_unpublished=True,
        )
        approve_report(
            db,
            report=report,
            actor=user,
            context=context,
            expected_version=payload.expected_lifecycle_version,
            note=payload.note,
        )
        db.commit()
        db.refresh(report)
        return report_payload(report)
    except ReportError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.post("/reports/{report_id}/publish", response_model=ReportOut)
def publish_approved_report(
    report_id: str,
    payload: ReportDecisionRequest,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        report = get_authorized_report(
            db,
            context=context,
            report_id=report_id,
            permission="report:publish",
            include_unpublished=True,
        )
        publish_report(
            db,
            report=report,
            actor=user,
            expected_version=payload.expected_lifecycle_version,
            note=payload.note,
        )
        db.commit()
        db.refresh(report)
        return report_payload(report)
    except ReportError as exc:
        db.rollback()
        raise _http_error(exc) from exc


@router.get("/reports/{report_id}/download")
def download_published_report(
    report_id: str,
    user: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        report = get_authorized_report(db, context=context, report_id=report_id)
        content, filename = download_report(db, report=report)
        record_report_download(db, report=report, actor=user)
        db.commit()
    except ReportError as exc:
        db.rollback()
        raise _http_error(exc) from exc
    safe_filename = (
        re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-") or "report.pdf"
    )
    return StreamingResponse(
        BytesIO(content),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
    )


__all__ = ["router"]
