"""Event Grid ingress and privileged durable-event operations."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.deps import require_admin
from app.integrations.events.azure_event_grid import (
    EventGridPayloadError,
    parse_event_grid_batch,
)
from app.models import EventDeliveryAttempt, EventOutbox, User
from app.services.blob_ingestion import enqueue_blob_ingestion_batch
from app.services.event_consumers import default_event_consumers
from app.services.event_outbox import dispatch_pending_events, requeue_dead_letter
from app.workers.event_worker import default_worker_id


router = APIRouter(prefix="/integrations/events", tags=["integrations"])


@router.post("/azure/blob-created")
async def azure_blob_created(request: Request, db: Session = Depends(get_db)):
    """Normalize an authenticated Event Grid delivery and enqueue ingestion."""

    try:
        payload = await request.json()
        batch = parse_event_grid_batch(
            payload,
            headers=request.headers,
            config=settings,
        )
    except (json.JSONDecodeError, EventGridPayloadError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Event Grid delivery was rejected") from exc
    if batch.validation_code is not None:
        return {"validationResponse": batch.validation_code}
    try:
        stats = enqueue_blob_ingestion_batch(db, batch.notifications)
        db.commit()
        return stats
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="Blob ingestion could not be queued") from exc


@router.get("/outbox/status")
def outbox_status(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(EventOutbox.status, func.count(EventOutbox.id)).group_by(EventOutbox.status)
    counts = {status: count for status, count in rows.all()}
    return {
        "provider": settings.queue_provider,
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "retry": counts.get("retry", 0),
        "published": counts.get("published", 0),
        "dead_letter": counts.get("dead_letter", 0),
    }


@router.get("/dead-letter")
def dead_letters(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(EventOutbox)
        .filter(EventOutbox.status == "dead_letter")
        .order_by(EventOutbox.dead_lettered_at.desc(), EventOutbox.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "aggregate_type": row.aggregate_type,
            "aggregate_id": row.aggregate_id,
            "correlation_id": row.correlation_id,
            "attempts": row.publish_attempts,
            "last_error": row.last_error,
            "dead_lettered_at": row.dead_lettered_at,
        }
        for row in rows
    ]


@router.post("/dead-letter/{event_id}/requeue")
def requeue(
    event_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = requeue_dead_letter(db, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Dead-letter event was not found")
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/dispatch")
def dispatch_once(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return dispatch_pending_events(
        db,
        worker_id=default_worker_id(),
        registry=default_event_consumers(),
        config=settings,
    )


@router.get("/outbox/{event_id}/attempts")
def delivery_attempts(
    event_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if db.get(EventOutbox, event_id) is None:
        raise HTTPException(status_code=404, detail="Event was not found")
    rows = (
        db.query(EventDeliveryAttempt)
        .filter(EventDeliveryAttempt.event_id == event_id)
        .order_by(EventDeliveryAttempt.attempt_number, EventDeliveryAttempt.created_at)
        .all()
    )
    return [
        {
            "attempt_number": row.attempt_number,
            "worker_id": row.worker_id,
            "provider": row.provider,
            "outcome": row.outcome,
            "error_code": row.error_code,
            "error_message": row.error_message,
            "created_at": row.created_at,
        }
        for row in rows
    ]


__all__ = ["router"]
