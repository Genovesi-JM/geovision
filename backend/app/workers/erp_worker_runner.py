"""Transaction-free orchestration for durable, provider-pinned ERP writes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from app.core.integration import (
    IntegrationError,
    IntegrationFailure,
    IntegrationResult,
)
from app.core.time import utc_now
from app.modules.orders.ports import (
    ERPCommand,
    ERPProvider,
    ERPWriteResult,
    as_erp_write_result,
)


@dataclass(frozen=True, slots=True)
class ErpClaim:
    outbox_id: str
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class ErpLease:
    outbox_id: str
    provider_name: str
    command: ERPCommand
    attempts: int
    max_attempts: int


class ErpRevalidationStatus(str, Enum):
    READY = "ready"
    DEAD_LETTERED = "dead_lettered"
    CLAIM_LOST = "claim_lost"


@dataclass(frozen=True, slots=True)
class ErpRevalidation:
    status: ErpRevalidationStatus
    lease: ErpLease | None = None

    def __post_init__(self) -> None:
        if (self.status is ErpRevalidationStatus.READY) != (self.lease is not None):
            raise ValueError("only ready ERP work can contain a lease")


class ErpRepository(Protocol):
    """Persistence boundary; every operation owns a short transaction."""

    def claim_batch(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
        lease_seconds: int,
    ) -> Sequence[ErpClaim]: ...

    def revalidate(
        self,
        *,
        worker_id: str,
        outbox_id: str,
        now: datetime,
    ) -> ErpRevalidation: ...

    def mark_completed(
        self,
        *,
        worker_id: str,
        lease: ErpLease,
        result: ERPWriteResult,
        now: datetime,
    ) -> bool: ...

    def mark_failed(
        self,
        *,
        worker_id: str,
        lease: ErpLease,
        failure: IntegrationFailure,
        terminal: bool,
        retry_at: datetime | None,
        now: datetime,
    ) -> bool: ...


ProviderResolver = Callable[[str], ERPProvider]


def _retry_delay(
    *,
    attempts: int,
    initial_seconds: float,
    maximum_seconds: float,
    requested_seconds: float | None,
) -> float:
    calculated = min(maximum_seconds, initial_seconds * (2 ** max(0, attempts - 1)))
    if requested_seconds is not None:
        calculated = max(calculated, min(maximum_seconds, requested_seconds))
    return max(0.0, calculated)


def run_erp_cycle(
    repository: ErpRepository,
    *,
    worker_id: str,
    provider_resolver: ProviderResolver,
    batch_size: int = 50,
    lease_seconds: int = 300,
    retry_initial_seconds: float = 0.5,
    retry_max_seconds: float = 8.0,
    clock: Callable[[], datetime] = utc_now,
) -> dict[str, int]:
    """Process a claimed batch without holding DB locks during provider I/O."""

    claims = repository.claim_batch(
        worker_id=worker_id,
        now=clock(),
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    stats = {
        "claimed": len(claims),
        "completed": 0,
        "retried": 0,
        "dead_lettered": 0,
        "claim_lost": 0,
    }
    providers: dict[str, ERPProvider] = {}
    for claim in claims:
        checked = repository.revalidate(
            worker_id=worker_id,
            outbox_id=claim.outbox_id,
            now=clock(),
        )
        if checked.status is ErpRevalidationStatus.DEAD_LETTERED:
            stats["dead_lettered"] += 1
            continue
        if checked.status is not ErpRevalidationStatus.READY or checked.lease is None:
            stats["claim_lost"] += 1
            continue
        lease = checked.lease
        try:
            provider = providers.get(lease.provider_name)
            if provider is None:
                provider = provider_resolver(lease.provider_name)
                if provider.provider_name != lease.provider_name:
                    raise IntegrationError(
                        provider=lease.provider_name,
                        operation="initialize",
                        code="provider_mismatch",
                        message="Resolved ERP provider does not match the pinned provider",
                        retryable=False,
                    )
                providers[lease.provider_name] = provider
            provider_payload = dict(lease.command.values)
            provider_payload.update(
                {
                    "geovision_id": lease.command.internal_id,
                    "organization_id": lease.command.organization_id,
                    "source_event": lease.command.source_event,
                }
            )
            provider_result = provider.upsert(
                lease.command.resource_type,
                provider_payload,
                lease.command.idempotency_key,
            )
            if provider_result.provider != lease.provider_name:
                raise IntegrationError(
                    provider=lease.provider_name,
                    operation="upsert",
                    code="provider_mismatch",
                    message="ERP result does not match the pinned provider",
                    retryable=False,
                )
        except IntegrationError as exc:
            provider_result = IntegrationResult.failed(
                provider=lease.provider_name,
                operation="upsert",
                failure=exc.as_failure(),
            )
        except Exception:
            # Provider exceptions may contain credentials or customer data.
            provider_result = IntegrationResult.failed(
                provider=lease.provider_name,
                operation="upsert",
                failure=IntegrationFailure(
                    code="erp_provider_error",
                    message="ERP provider request failed unexpectedly",
                    retryable=True,
                ),
            )

        finished_at = clock()
        if provider_result.ok:
            try:
                write_result = as_erp_write_result(provider_result.value)
            except ValueError:
                provider_result = IntegrationResult.failed(
                    provider=lease.provider_name,
                    operation="upsert",
                    failure=IntegrationFailure(
                        code="erp_response_invalid",
                        message="ERP provider did not return an external reference",
                        retryable=True,
                    ),
                )
            else:
                try:
                    persisted = repository.mark_completed(
                        worker_id=worker_id,
                        lease=lease,
                        result=write_result,
                        now=finished_at,
                    )
                except Exception:
                    provider_result = IntegrationResult.failed(
                        provider=lease.provider_name,
                        operation="persist_result",
                        failure=IntegrationFailure(
                            code="erp_result_persistence_failed",
                            message="ERP result could not be persisted",
                            retryable=True,
                        ),
                    )
                else:
                    if persisted:
                        stats["completed"] += 1
                    else:
                        stats["claim_lost"] += 1
                    continue

        failure = provider_result.failure or IntegrationFailure(
            code="erp_provider_failed",
            message="ERP provider request failed",
            retryable=True,
        )
        terminal = not failure.retryable or lease.attempts >= lease.max_attempts
        retry_at = None
        if not terminal:
            retry_at = finished_at + timedelta(
                seconds=_retry_delay(
                    attempts=lease.attempts,
                    initial_seconds=retry_initial_seconds,
                    maximum_seconds=retry_max_seconds,
                    requested_seconds=failure.retry_after_seconds,
                )
            )
        try:
            failure_persisted = repository.mark_failed(
                worker_id=worker_id,
                lease=lease,
                failure=failure,
                terminal=terminal,
                retry_at=retry_at,
                now=finished_at,
            )
        except Exception:
            failure_persisted = False
        if failure_persisted:
            stats["dead_lettered" if terminal else "retried"] += 1
        else:
            stats["claim_lost"] += 1
    return stats


__all__ = [
    "ErpClaim",
    "ErpLease",
    "ErpRepository",
    "ErpRevalidation",
    "ErpRevalidationStatus",
    "run_erp_cycle",
]
