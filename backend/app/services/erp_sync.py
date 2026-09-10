from __future__ import annotations

import json
from datetime import timedelta
import re
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.event_names import EventNames
from app.core.integration import (
    IntegrationError,
    IntegrationFailure,
    RetryPolicy,
)
from app.core.time import utc_now
from app.models import AccountEvent, ErpExternalReference, IntegrationOutbox
from app.modules.orders.ports import ERPProvider, as_erp_write_result


_ACCOUNT_EVENT_SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|credential|password|passwd|secret|token|"
    r"access_token|refresh_token|api_key|private_key|connection_string|sas_key|"
    r"signature|client_secret)s?($|_)",
    re.IGNORECASE,
)


def _reject_sensitive_account_event_payload(
    value: object,
    *,
    path: str = "payload",
) -> None:
    """Keep credential-shaped fields out of customer-visible account history."""

    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).strip("_")
            normalized = re.sub(
                r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
                "_",
                normalized,
            )
            if _ACCOUNT_EVENT_SENSITIVE_KEY.search(normalized):
                raise ValueError(
                    f"{path} cannot contain credential-like key '{key}'"
                )
            _reject_sensitive_account_event_payload(
                nested,
                path=f"{path}.{key}",
            )
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_sensitive_account_event_payload(
                nested,
                path=f"{path}[{index}]",
            )


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
        _enqueue_erp_signal(db, existing)
        return existing
    item = IntegrationOutbox(
        company_id=company_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload_json=json.dumps(payload, default=str),
        idempotency_key=key,
        provider=provider or settings.erp_provider,
        max_attempts=settings.integration_retry_attempts,
    )
    db.add(item)
    db.flush()
    _enqueue_erp_signal(db, item)
    return item


def _enqueue_erp_signal(db: Session, item: IntegrationOutbox) -> None:
    from app.services.event_outbox import enqueue_domain_event

    enqueue_domain_event(
        db,
        name=EventNames.ERP_SYNC_REQUESTED,
        aggregate_type="integration_outbox",
        aggregate_id=item.id,
        idempotency_key=f"erp-outbox:{item.id}",
        correlation_id=item.id,
        payload={
            "integration_outbox_id": item.id,
            "organization_id": item.company_id,
            "provider": item.provider,
            "resource_type": item.aggregate_type,
            "resource_id": item.aggregate_id,
            "source_event": item.event_type,
        },
    )


def publish_account_event(
    db: Session,
    *,
    company_id: str,
    workspace_id: str | None = None,
    event_type: str,
    resource_type: str,
    resource_id: str | None,
    title: str,
    payload: dict[str, Any] | None = None,
) -> AccountEvent:
    safe_payload = payload or {}
    _reject_sensitive_account_event_payload(safe_payload)
    event = AccountEvent(
        company_id=company_id,
        workspace_id=workspace_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        title=title,
        payload_json=json.dumps(safe_payload, default=str),
    )
    db.add(event)
    return event


def _policy(retry_policy: RetryPolicy | None = None) -> RetryPolicy:
    return retry_policy or RetryPolicy(
        max_attempts=settings.integration_retry_attempts,
        initial_delay_seconds=settings.integration_retry_initial_seconds,
        max_delay_seconds=settings.integration_retry_max_seconds,
    )


def process_outbox_item(
    db: Session,
    item: IntegrationOutbox,
    *,
    provider: ERPProvider,
    retry_policy: RetryPolicy | None = None,
) -> str:
    """Process one pinned ERP item without committing the caller's transaction."""

    policy = _policy(retry_policy)
    if item.status == "completed":
        return "completed"
    if item.status in {"failed_terminal", "dead_letter"}:
        return "failed_terminal"
    if item.provider != provider.provider_name:
        raise IntegrationError(
            provider=provider.provider_name,
            operation="upsert",
            code="provider_mismatch",
            message="ERP outbox item is pinned to another provider",
            retryable=False,
        )
    item.attempts += 1
    item.status = "processing"
    try:
        provider_payload = json.loads(item.payload_json or "{}")
        if not isinstance(provider_payload, dict):
            raise ValueError("ERP payload must be a JSON object")
        provider_payload.update(
            {
                "geovision_id": item.aggregate_id,
                "organization_id": item.company_id,
                "source_event": item.event_type,
            }
        )
        result = provider.upsert(
            item.aggregate_type,
            provider_payload,
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
        write_result = as_erp_write_result(result.value)
        item.external_id = write_result.external_id
        item.external_model = write_result.external_model
        item.status = "completed"
        item.processed_at = utc_now()
        item.last_error = None
        item.last_error_code = None
        item.next_attempt_at = None
        item.dead_lettered_at = None
        reference = (
            db.query(ErpExternalReference)
            .filter(
                ErpExternalReference.provider == item.provider,
                ErpExternalReference.resource_type == item.aggregate_type,
                ErpExternalReference.internal_id == item.aggregate_id,
            )
            .one_or_none()
        )
        if reference is None:
            reference = ErpExternalReference(
                company_id=item.company_id,
                provider=item.provider,
                resource_type=item.aggregate_type,
                internal_id=item.aggregate_id,
                external_id=write_result.external_id,
            )
            db.add(reference)
        reference.external_id = write_result.external_id
        reference.external_model = write_result.external_model
        reference.invoice_status = (
            write_result.invoice_status
            if write_result.invoice_status is not None
            else reference.invoice_status
        )
        reference.stock_status = (
            write_result.stock_status
            if write_result.stock_status is not None
            else reference.stock_status
        )
        reference.purchase_status = (
            write_result.purchase_status
            if write_result.purchase_status is not None
            else reference.purchase_status
        )
        reference.provider_updated_at = utc_now()
        return "completed"
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
        item.last_error_code = failure.code
        may_retry = policy.allows_retry(
            attempts_made=item.attempts,
            failure=failure,
            operation_is_idempotent=False,
            idempotency_key=item.idempotency_key,
        ) and item.attempts < item.max_attempts
        if may_retry:
            item.status = "failed"
            delay = policy.delay_after(
                item.attempts,
                retry_after_seconds=failure.retry_after_seconds,
            )
            item.next_attempt_at = utc_now() + timedelta(seconds=delay)
            return "failed"
        item.status = "failed_terminal"
        item.next_attempt_at = None
        item.dead_lettered_at = utc_now()
        return "failed_terminal"


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
    policy = _policy(retry_policy)
    now = utc_now()
    pending = (
        db.query(IntegrationOutbox)
        .filter(IntegrationOutbox.attempts < policy.max_attempts)
        .filter(IntegrationOutbox.attempts < IntegrationOutbox.max_attempts)
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
        outcome = process_outbox_item(
            db,
            item,
            provider=provider,
            retry_policy=policy,
        )
        if outcome == "completed":
            completed += 1
        else:
            failed += 1
    db.commit()
    return {"processed": len(pending), "completed": completed, "failed": failed}


__all__ = [
    "enqueue_erp_event",
    "process_outbox_item",
    "process_pending",
    "publish_account_event",
]
