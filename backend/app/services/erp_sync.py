from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.integration import (
    IntegrationError,
    IntegrationFailure,
    RetryPolicy,
)
from app.core.time import utc_now
from app.models import AccountEvent, IntegrationOutbox
from app.modules.orders.ports import ERPProvider


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
    provider: str | None = None,
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
        provider=provider or settings.erp_provider,
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


def process_pending(
    db: Session,
    limit: int = 50,
    provider: ERPProvider | None = None,
    retry_policy: RetryPolicy | None = None,
) -> dict[str, int]:
    """Process due ERP work through an injectable, idempotent provider port."""

    if provider is None:
        from app.integrations.erp import get_erp_adapter

        provider = get_erp_adapter()
    policy = retry_policy or RetryPolicy(
        max_attempts=settings.integration_retry_attempts,
        initial_delay_seconds=settings.integration_retry_initial_seconds,
        max_delay_seconds=settings.integration_retry_max_seconds,
    )
    now = utc_now()
    pending = (
        db.query(IntegrationOutbox)
        .filter(IntegrationOutbox.attempts < policy.max_attempts)
        .filter(IntegrationOutbox.provider == provider.provider_name)
        .filter(
            or_(
                and_(
                    IntegrationOutbox.status == "pending",
                    IntegrationOutbox.next_attempt_at.is_(None),
                ),
                and_(
                    IntegrationOutbox.status == "failed",
                    or_(
                        IntegrationOutbox.next_attempt_at.is_(None),
                        IntegrationOutbox.next_attempt_at <= now,
                    ),
                ),
            )
        )
        .order_by(IntegrationOutbox.created_at.asc())
        .limit(limit)
        .all()
    )
    completed = failed = 0
    for item in pending:
        item.attempts += 1
        item.status = "processing"
        try:
            result = provider.upsert(
                ERP_DOCTYPE.get(item.aggregate_type, item.aggregate_type),
                json.loads(item.payload_json or "{}"),
                item.idempotency_key,
            )
            if not result.ok or not result.value:
                failure = result.failure or IntegrationFailure(
                    code="provider_failed",
                    message="ERP provider did not return an external reference",
                )
                raise IntegrationError(
                    provider=provider.provider_name,
                    operation="upsert",
                    code=failure.code,
                    message=failure.message,
                    retryable=failure.retryable,
                    retry_after_seconds=failure.retry_after_seconds,
                )
            item.external_id = result.value
            item.status = "completed"
            item.processed_at = utc_now()
            item.last_error = None
            item.next_attempt_at = None
            completed += 1
        except Exception as exc:
            failure = (
                exc.as_failure()
                if isinstance(exc, IntegrationError)
                else IntegrationFailure(
                    code="provider_error",
                    message="ERP provider request failed unexpectedly",
                    retryable=False,
                )
            )
            item.last_error = failure.message
            if policy.allows_retry(
                attempts_made=item.attempts,
                failure=failure,
                operation_is_idempotent=False,
                idempotency_key=item.idempotency_key,
            ):
                item.status = "failed"
                delay = policy.delay_after(
                    item.attempts,
                    retry_after_seconds=failure.retry_after_seconds,
                )
                item.next_attempt_at = utc_now() + timedelta(seconds=delay)
            else:
                item.status = "failed_terminal"
                item.next_attempt_at = None
            failed += 1
    db.commit()
    return {"processed": len(pending), "completed": completed, "failed": failed}
