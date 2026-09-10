"""SQLAlchemy persistence binding for the independent ERP worker."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
import json

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.integration import IntegrationFailure
from app.models import ErpExternalReference, IntegrationOutbox
from app.modules.orders.ports import ERPCommand, ERPWriteResult
from app.services.event_outbox import enqueue_domain_event
from app.workers.erp_worker_runner import (
    ErpClaim,
    ErpLease,
    ErpRevalidation,
    ErpRevalidationStatus,
)


_SUPPORTED_RESOURCE_TYPES = frozenset(
    {
        "customer",
        "product",
        "service",
        "order",
        "invoice",
        "payment",
        "delivery",
        "supplier",
        "purchase_order",
        "inventory",
    }
)


def _clear_claim(row: IntegrationOutbox) -> None:
    row.claimed_by = None
    row.claimed_at = None
    row.lease_expires_at = None


class SqlAlchemyErpRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def claim_batch(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
        lease_seconds: int,
    ) -> Sequence[ErpClaim]:
        claims: list[ErpClaim] = []
        with self._session_factory() as db, db.begin():
            stale = (
                db.execute(
                    select(IntegrationOutbox)
                    .where(
                        IntegrationOutbox.status == "processing",
                        IntegrationOutbox.lease_expires_at.is_not(None),
                        IntegrationOutbox.lease_expires_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
                .scalars()
                .all()
            )
            for row in stale:
                _clear_claim(row)
                row.updated_at = now
                if row.attempts >= row.max_attempts:
                    row.status = "dead_letter"
                    row.dead_lettered_at = now
                    row.last_error_code = "erp_lease_expired"
                    row.last_error = "ERP worker lease expired"
                else:
                    row.status = "failed"
                    row.next_attempt_at = now

            due = (
                db.execute(
                    select(IntegrationOutbox)
                    .where(
                        IntegrationOutbox.status.in_(("pending", "failed")),
                        IntegrationOutbox.attempts < IntegrationOutbox.max_attempts,
                        or_(
                            IntegrationOutbox.next_attempt_at.is_(None),
                            IntegrationOutbox.next_attempt_at <= now,
                        ),
                    )
                    .order_by(
                        IntegrationOutbox.next_attempt_at.asc(),
                        IntegrationOutbox.created_at.asc(),
                        IntegrationOutbox.id.asc(),
                    )
                    .limit(max(1, min(batch_size, 500)))
                    .with_for_update(skip_locked=True)
                )
                .scalars()
                .all()
            )
            for row in due:
                row.status = "processing"
                row.claimed_by = worker_id[:100]
                row.claimed_at = now
                row.lease_expires_at = now + timedelta(seconds=max(30, lease_seconds))
                row.next_attempt_at = None
                row.attempts += 1
                row.updated_at = now
                claims.append(
                    ErpClaim(
                        outbox_id=row.id,
                        attempts=row.attempts,
                        max_attempts=row.max_attempts,
                    )
                )
        return claims

    @staticmethod
    def _claimed_row(
        db: Session,
        *,
        outbox_id: str,
        worker_id: str,
        now: datetime,
    ) -> IntegrationOutbox | None:
        row = db.execute(
            select(IntegrationOutbox)
            .where(IntegrationOutbox.id == outbox_id)
            .with_for_update()
        ).scalar_one_or_none()
        if (
            row is None
            or row.status != "processing"
            or row.claimed_by != worker_id[:100]
            or row.lease_expires_at is None
            or row.lease_expires_at <= now
        ):
            return None
        return row

    @staticmethod
    def _dead_letter_invalid(
        row: IntegrationOutbox,
        *,
        now: datetime,
        code: str,
        message: str,
    ) -> ErpRevalidation:
        row.status = "dead_letter"
        row.last_error_code = code
        row.last_error = message
        row.dead_lettered_at = now
        row.updated_at = now
        _clear_claim(row)
        return ErpRevalidation(ErpRevalidationStatus.DEAD_LETTERED)

    def revalidate(
        self,
        *,
        worker_id: str,
        outbox_id: str,
        now: datetime,
    ) -> ErpRevalidation:
        with self._session_factory() as db, db.begin():
            row = self._claimed_row(
                db,
                outbox_id=outbox_id,
                worker_id=worker_id,
                now=now,
            )
            if row is None:
                return ErpRevalidation(ErpRevalidationStatus.CLAIM_LOST)
            resource_type = row.aggregate_type.strip().lower()
            if resource_type not in _SUPPORTED_RESOURCE_TYPES:
                return self._dead_letter_invalid(
                    row,
                    now=now,
                    code="erp_resource_unsupported",
                    message="ERP resource type is not supported",
                )
            try:
                payload = json.loads(row.payload_json or "{}")
            except (TypeError, ValueError):
                payload = None
            if not isinstance(payload, dict):
                return self._dead_letter_invalid(
                    row,
                    now=now,
                    code="erp_payload_invalid",
                    message="ERP payload must be a JSON object",
                )
            return ErpRevalidation(
                ErpRevalidationStatus.READY,
                ErpLease(
                    outbox_id=row.id,
                    provider_name=row.provider,
                    command=ERPCommand(
                        resource_type=resource_type,
                        internal_id=row.aggregate_id,
                        organization_id=row.company_id,
                        source_event=row.event_type,
                        idempotency_key=row.idempotency_key,
                        values=payload,
                    ),
                    attempts=row.attempts,
                    max_attempts=row.max_attempts,
                ),
            )

    def mark_completed(
        self,
        *,
        worker_id: str,
        lease: ErpLease,
        result: ERPWriteResult,
        now: datetime,
    ) -> bool:
        with self._session_factory() as db, db.begin():
            row = self._claimed_row(
                db,
                outbox_id=lease.outbox_id,
                worker_id=worker_id,
                now=now,
            )
            if row is None:
                return False
            reference = (
                db.query(ErpExternalReference)
                .filter(
                    ErpExternalReference.provider == row.provider,
                    ErpExternalReference.resource_type == row.aggregate_type,
                    ErpExternalReference.internal_id == row.aggregate_id,
                )
                .one_or_none()
            )
            if reference is None:
                reference = ErpExternalReference(
                    company_id=row.company_id,
                    provider=row.provider,
                    resource_type=row.aggregate_type,
                    internal_id=row.aggregate_id,
                    external_id=result.external_id,
                )
                db.add(reference)
            reference.external_id = result.external_id
            reference.external_model = result.external_model
            if result.invoice_status is not None:
                reference.invoice_status = result.invoice_status
            if result.stock_status is not None:
                reference.stock_status = result.stock_status
            if result.purchase_status is not None:
                reference.purchase_status = result.purchase_status
            reference.provider_updated_at = now
            reference.updated_at = now

            row.external_id = result.external_id
            row.external_model = result.external_model
            row.status = "completed"
            row.processed_at = now
            row.updated_at = now
            row.last_error = None
            row.last_error_code = None
            row.next_attempt_at = None
            row.dead_lettered_at = None
            _clear_claim(row)
            enqueue_domain_event(
                db,
                name=EventNames.ERP_SYNC_COMPLETED,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                idempotency_key=f"erp-result:{row.id}:completed",
                correlation_id=row.id,
                payload={
                    "integration_outbox_id": row.id,
                    "organization_id": row.company_id,
                    "provider": row.provider,
                    "external_reference": result.external_id,
                    "outcome": "completed",
                },
            )
            return True

    def mark_failed(
        self,
        *,
        worker_id: str,
        lease: ErpLease,
        failure: IntegrationFailure,
        terminal: bool,
        retry_at: datetime | None,
        now: datetime,
    ) -> bool:
        with self._session_factory() as db, db.begin():
            row = self._claimed_row(
                db,
                outbox_id=lease.outbox_id,
                worker_id=worker_id,
                now=now,
            )
            if row is None:
                return False
            row.status = "dead_letter" if terminal else "failed"
            row.last_error_code = failure.code[:100]
            row.last_error = failure.message
            row.next_attempt_at = None if terminal else retry_at
            row.dead_lettered_at = now if terminal else None
            row.updated_at = now
            _clear_claim(row)
            enqueue_domain_event(
                db,
                name=EventNames.ERP_SYNC_FAILED,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                idempotency_key=f"erp-result:{row.id}:{row.status}:{row.attempts}",
                correlation_id=row.id,
                payload={
                    "integration_outbox_id": row.id,
                    "organization_id": row.company_id,
                    "provider": row.provider,
                    "outcome": row.status,
                    "error_code": failure.code,
                },
            )
            return True

    def requeue_dead_letter(self, outbox_id: str, *, now: datetime) -> bool:
        with self._session_factory() as db, db.begin():
            row = db.execute(
                select(IntegrationOutbox)
                .where(IntegrationOutbox.id == outbox_id)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None or row.status not in {"dead_letter", "failed_terminal"}:
                return False
            row.status = "pending"
            row.attempts = 0
            row.next_attempt_at = now
            row.dead_lettered_at = None
            row.last_error = None
            row.last_error_code = None
            row.updated_at = now
            _clear_claim(row)
            return True


__all__ = ["SqlAlchemyErpRepository"]
