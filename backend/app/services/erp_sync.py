from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.integrations.erp import get_erp_adapter
from app.models import AccountEvent, IntegrationOutbox


ERP_DOCTYPE = {
    "customer": "Customer",
    "product": "Item",
    "order": "Sales Order",
    "invoice": "Sales Invoice",
    "payment": "Payment Entry",
    "delivery": "Delivery Note",
}


def enqueue_erp_event(
    db: Session,
    *,
    company_id: str | None,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict[str, Any],
    version: str,
) -> IntegrationOutbox:
    key = f"{aggregate_type}:{aggregate_id}:{event_type}:{version}"
    existing = db.query(IntegrationOutbox).filter_by(idempotency_key=key).first()
    if existing:
        return existing
    item = IntegrationOutbox(
        company_id=company_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload_json=json.dumps(payload, default=str),
        idempotency_key=key,
    )
    db.add(item)
    return item


def publish_account_event(
    db: Session,
    *,
    company_id: str,
    event_type: str,
    resource_type: str,
    resource_id: str | None,
    title: str,
    payload: dict[str, Any] | None = None,
) -> AccountEvent:
    event = AccountEvent(
        company_id=company_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        title=title,
        payload_json=json.dumps(payload or {}, default=str),
    )
    db.add(event)
    return event


def process_pending(db: Session, limit: int = 50) -> dict[str, int]:
    adapter = get_erp_adapter()
    pending = (
        db.query(IntegrationOutbox)
        .filter(IntegrationOutbox.status.in_(["pending", "failed"]))
        .order_by(IntegrationOutbox.created_at.asc())
        .limit(limit)
        .all()
    )
    completed = failed = 0
    for item in pending:
        item.attempts += 1
        item.status = "processing"
        try:
            result = adapter.upsert(
                ERP_DOCTYPE.get(item.aggregate_type, item.aggregate_type),
                json.loads(item.payload_json or "{}"),
                item.idempotency_key,
            )
            item.external_id = result.external_id
            item.status = "completed"
            item.processed_at = datetime.utcnow()
            item.last_error = None
            completed += 1
        except Exception as exc:
            item.status = "failed"
            item.last_error = str(exc)[:1000]
            failed += 1
    db.commit()
    return {"processed": len(pending), "completed": completed, "failed": failed}
