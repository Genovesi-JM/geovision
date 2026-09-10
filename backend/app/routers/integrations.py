"""ERP operations, safe status projections, and authenticated callbacks."""

from datetime import datetime
import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.integration import IntegrationError
from app.core.time import utc_now
from app.deps import get_current_user, require_admin
from app.integrations.erp import get_erp_adapter
from app.models import ErpExternalReference, IntegrationOutbox, User
from app.modules.organizations.services import get_user_company_id
from app.services.erp_callbacks import (
    ErpCallbackError,
    apply_odoo_status_callback,
    verify_callback_signature,
)
from app.services.erp_sync import process_pending

_get_user_company_id = get_user_company_id

router = APIRouter(prefix="/integrations/erp", tags=["integrations"])


class OdooStatusCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=160)
    event_type: str = Field(
        pattern="^(order|invoice|stock|purchase)\\.status$",
        max_length=80,
    )
    resource_type: str = Field(
        pattern="^(order|invoice|product|service|purchase_order|inventory)$"
    )
    geovision_id: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=200)
    external_model: str | None = Field(default=None, max_length=120)
    invoice_status: str | None = Field(default=None, min_length=1, max_length=100)
    stock_status: str | None = Field(default=None, min_length=1, max_length=100)
    purchase_status: str | None = Field(default=None, min_length=1, max_length=100)
    provider_updated_at: datetime | None = None

    @model_validator(mode="after")
    def status_is_present(self) -> "OdooStatusCallback":
        if not any(
            (self.invoice_status, self.stock_status, self.purchase_status)
        ):
            raise ValueError("at least one ERP projection status is required")
        required_field = {
            "invoice.status": self.invoice_status,
            "stock.status": self.stock_status,
            "purchase.status": self.purchase_status,
        }.get(self.event_type)
        if self.event_type != "order.status" and required_field is None:
            raise ValueError("callback event type does not match its status field")
        return self


@router.get("/status")
def status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        provider = get_erp_adapter().health()
    except IntegrationError as exc:
        provider = {
            "provider": exc.provider,
            "configured": False,
            "mode": "blocked",
            "code": exc.code,
            "reason": exc.safe_message,
        }
    company_id = _get_user_company_id(user, db)
    queue = db.query(IntegrationOutbox).filter(IntegrationOutbox.company_id == company_id)
    provider_counts = {
        provider: count
        for provider, count in queue.with_entities(
            IntegrationOutbox.provider,
            func.count(IntegrationOutbox.id),
        )
        .group_by(IntegrationOutbox.provider)
        .all()
    }
    oldest = (
        queue.filter(IntegrationOutbox.status.in_(["pending", "failed"]))
        .order_by(IntegrationOutbox.created_at.asc())
        .first()
    )
    return {
        **provider,
        "pending": queue.filter(IntegrationOutbox.status == "pending").count(),
        "processing": queue.filter(IntegrationOutbox.status == "processing").count(),
        "retrying": queue.filter(IntegrationOutbox.status == "failed").count(),
        "failed": queue.filter(
            IntegrationOutbox.status.in_(["failed", "failed_terminal", "dead_letter"])
        ).count(),
        "dead_lettered": queue.filter(
            IntegrationOutbox.status.in_(["failed_terminal", "dead_letter"])
        ).count(),
        "by_provider": provider_counts,
        "oldest_pending_at": oldest.created_at if oldest else None,
    }


@router.post("/sync")
def sync(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return process_pending(db)
    except IntegrationError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"ERP provider is unavailable: {exc.safe_message}",
        ) from exc


@router.get("/outbox")
def list_outbox(
    limit: int = 100,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    rows = (
        db.query(IntegrationOutbox)
        .filter(IntegrationOutbox.company_id == company_id)
        .order_by(IntegrationOutbox.created_at.desc())
        .limit(max(1, min(limit, 250)))
        .all()
    )
    return [
        {
            "id": row.id,
            "geovision_id": row.aggregate_id,
            "resource_type": row.aggregate_type,
            "source_event": row.event_type,
            "provider": row.provider,
            "status": row.status,
            "attempts": row.attempts,
            "max_attempts": row.max_attempts,
            "error_code": row.last_error_code,
            "error": row.last_error,
            "next_attempt_at": row.next_attempt_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


@router.post("/outbox/{outbox_id}/requeue")
def requeue_outbox(
    outbox_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    row = (
        db.query(IntegrationOutbox)
        .filter(
            IntegrationOutbox.id == outbox_id,
            IntegrationOutbox.company_id == company_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="ERP sync item not found")
    if row.status not in {"dead_letter", "failed_terminal"}:
        raise HTTPException(status_code=409, detail="ERP sync item is not dead-lettered")
    row.status = "pending"
    row.attempts = 0
    row.next_attempt_at = utc_now()
    row.dead_lettered_at = None
    row.last_error = None
    row.last_error_code = None
    row.claimed_by = None
    row.claimed_at = None
    row.lease_expires_at = None
    row.updated_at = utc_now()
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/references/{resource_type}/{internal_id}")
def reference_status(
    resource_type: str,
    internal_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company_id = _get_user_company_id(user, db)
    reference = (
        db.query(ErpExternalReference)
        .filter(
            ErpExternalReference.company_id == company_id,
            ErpExternalReference.resource_type == resource_type,
            ErpExternalReference.internal_id == internal_id,
        )
        .one_or_none()
    )
    if reference is None:
        pending = (
            db.query(IntegrationOutbox)
            .filter(
                IntegrationOutbox.company_id == company_id,
                IntegrationOutbox.aggregate_type == resource_type,
                IntegrationOutbox.aggregate_id == internal_id,
            )
            .order_by(IntegrationOutbox.created_at.desc())
            .first()
        )
        if pending is None:
            raise HTTPException(status_code=404, detail="ERP projection not found")
        return {
            "geovision_id": internal_id,
            "resource_type": resource_type,
            "sync_status": pending.status,
            "invoice_status": None,
            "stock_status": None,
            "purchase_status": None,
            "updated_at": pending.updated_at,
        }
    return {
        "geovision_id": reference.internal_id,
        "resource_type": reference.resource_type,
        "sync_status": "completed",
        "invoice_status": reference.invoice_status,
        "stock_status": reference.stock_status,
        "purchase_status": reference.purchase_status,
        "updated_at": reference.updated_at,
    }


@router.post("/odoo/callback")
async def odoo_callback(
    request: Request,
    x_geovision_timestamp: str = Header(alias="X-GeoVision-Timestamp"),
    x_geovision_signature: str = Header(alias="X-GeoVision-Signature"),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    if len(raw_body) > 64 * 1024:
        raise HTTPException(status_code=413, detail="Odoo callback body is too large")
    try:
        verify_callback_signature(
            raw_body,
            timestamp=x_geovision_timestamp,
            signature=x_geovision_signature,
            secret=settings.odoo_webhook_secret,
            replay_window_seconds=settings.erp_callback_replay_window_seconds,
        )
        parsed = OdooStatusCallback.model_validate_json(raw_body)
        outcome, reference = apply_odoo_status_callback(
            db,
            payload=parsed.model_dump(),
            payload_sha256=hashlib.sha256(raw_body).hexdigest(),
        )
        db.commit()
    except ErpCallbackError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.safe_message},
        ) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"code": "odoo_callback_invalid", "message": "Callback body is invalid"},
        ) from exc
    return {
        "status": outcome,
        "geovision_id": reference.internal_id,
        "resource_type": reference.resource_type,
    }
