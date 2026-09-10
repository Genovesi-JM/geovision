"""Transaction-free orchestration for claimed notification deliveries."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from app.core.integration import IntegrationFailure, IntegrationResult
from app.core.time import utc_now
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    ExternalDeliveryMessage,
    ExternalDeliveryProvider,
)


@dataclass(frozen=True, slots=True)
class DeliveryLease:
    message: ExternalDeliveryMessage
    provider_name: str
    attempts: int
    max_attempts: int

    def __post_init__(self) -> None:
        if self.attempts < 1 or self.max_attempts < 1:
            raise ValueError("delivery attempt counters must be positive")


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    delivery_id: str
    attempts: int
    max_attempts: int

    def __post_init__(self) -> None:
        if not self.delivery_id.strip():
            raise ValueError("delivery_id must not be empty")
        if self.attempts < 1 or self.max_attempts < 1:
            raise ValueError("delivery attempt counters must be positive")


class RevalidationStatus(str, Enum):
    READY = "ready"
    SUPPRESSED = "suppressed"
    DEFERRED = "deferred"
    DEAD_LETTERED = "dead_lettered"
    CLAIM_LOST = "claim_lost"


@dataclass(frozen=True, slots=True)
class Revalidation:
    status: RevalidationStatus
    lease: DeliveryLease | None = None

    def __post_init__(self) -> None:
        if (self.status is RevalidationStatus.READY) != (self.lease is not None):
            raise ValueError("only a ready revalidation can contain a lease")


class DeliveryRepository(Protocol):
    """Persistence boundary; every method owns and closes its transaction."""

    def claim_batch(
        self,
        *,
        worker_id: str,
        now: datetime,
        batch_size: int,
        lease_seconds: int,
    ) -> Sequence[DeliveryClaim]: ...

    def revalidate(
        self,
        *,
        worker_id: str,
        delivery_id: str,
        now: datetime,
    ) -> Revalidation: ...

    def mark_delivered(
        self,
        *,
        worker_id: str,
        lease: DeliveryLease,
        provider_message_id: str | None,
        now: datetime,
    ) -> bool: ...

    def mark_failed(
        self,
        *,
        worker_id: str,
        lease: DeliveryLease,
        failure: IntegrationFailure,
        terminal: bool,
        retry_at: datetime | None,
        now: datetime,
    ) -> bool: ...


ProviderResolver = Callable[[str, ExternalDeliveryMessage], ExternalDeliveryProvider]


def retry_delay_seconds(
    *,
    attempts: int,
    base_seconds: float,
    maximum_seconds: float,
    requested_seconds: float | None = None,
) -> float:
    calculated = min(maximum_seconds, base_seconds * (2 ** max(0, attempts - 1)))
    if requested_seconds is not None:
        calculated = max(calculated, min(requested_seconds, maximum_seconds))
    return max(0.0, calculated)


def run_delivery_cycle(
    repository: DeliveryRepository,
    *,
    worker_id: str,
    provider_resolver: ProviderResolver,
    batch_size: int = 50,
    lease_seconds: int = 300,
    retry_base_seconds: float = 30.0,
    retry_max_seconds: float = 3600.0,
    clock: Callable[[], datetime] = utc_now,
) -> dict[str, int]:
    """Claim, re-authorize, and deliver one batch without holding DB locks."""

    now = clock()
    leases = repository.claim_batch(
        worker_id=worker_id,
        now=now,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    stats = {
        "claimed": len(leases),
        "delivered": 0,
        "retried": 0,
        "dead_lettered": 0,
        "suppressed": 0,
        "claim_lost": 0,
    }
    providers: dict[tuple[str, str], ExternalDeliveryProvider] = {}

    stats["deferred"] = 0
    for originally_claimed in leases:
        checked = repository.revalidate(
            worker_id=worker_id,
            delivery_id=originally_claimed.delivery_id,
            now=clock(),
        )
        if checked.status is RevalidationStatus.SUPPRESSED:
            stats["suppressed"] += 1
            continue
        if checked.status is RevalidationStatus.DEFERRED:
            stats["deferred"] += 1
            continue
        if checked.status is RevalidationStatus.DEAD_LETTERED:
            stats["dead_lettered"] += 1
            continue
        if checked.status is RevalidationStatus.CLAIM_LOST or checked.lease is None:
            stats["claim_lost"] += 1
            continue
        lease = checked.lease
        cache_key = (lease.provider_name, lease.message.channel.value)
        try:
            provider = providers.get(cache_key)
            if provider is None:
                provider = provider_resolver(lease.provider_name, lease.message)
                providers[cache_key] = provider
            result = provider.deliver(lease.message)
        except Exception:
            # Provider exceptions can carry credentials and private routing data.
            result = IntegrationResult.failed(
                provider=lease.provider_name or "notification",
                operation="deliver",
                failure=IntegrationFailure(
                    code="notification_delivery_failed",
                    message="notification delivery provider raised an error",
                    retryable=True,
                ),
            )

        finished_at = clock()
        if result.ok:
            acknowledgement = result.value
            provider_message_id = (
                acknowledgement.provider_message_id
                if isinstance(acknowledgement, DeliveryAcknowledgement)
                else None
            )
            if repository.mark_delivered(
                worker_id=worker_id,
                lease=lease,
                provider_message_id=provider_message_id,
                now=finished_at,
            ):
                stats["delivered"] += 1
            else:
                stats["claim_lost"] += 1
            continue

        failure = result.failure or IntegrationFailure(
            code="notification_delivery_failed",
            message="notification delivery failed",
            retryable=True,
        )
        terminal = not failure.retryable or lease.attempts >= lease.max_attempts
        retry_at = None
        if not terminal:
            retry_at = finished_at + timedelta(
                seconds=retry_delay_seconds(
                    attempts=lease.attempts,
                    base_seconds=retry_base_seconds,
                    maximum_seconds=retry_max_seconds,
                    requested_seconds=failure.retry_after_seconds,
                )
            )
        if repository.mark_failed(
            worker_id=worker_id,
            lease=lease,
            failure=failure,
            terminal=terminal,
            retry_at=retry_at,
            now=finished_at,
        ):
            stats["dead_lettered" if terminal else "retried"] += 1
        else:
            stats["claim_lost"] += 1

    return stats


__all__ = [
    "DeliveryClaim",
    "DeliveryLease",
    "DeliveryRepository",
    "ProviderResolver",
    "Revalidation",
    "RevalidationStatus",
    "retry_delay_seconds",
    "run_delivery_cycle",
]
