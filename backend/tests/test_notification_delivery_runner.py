"""Durability, retry, and revalidation tests for the delivery worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.notifications.delivery_ports import (
    DeliveryAcknowledgement,
    DeliveryChannel,
    ExternalDeliveryMessage,
)
from app.workers.notification_delivery_runner import (
    DeliveryClaim,
    DeliveryLease,
    Revalidation,
    RevalidationStatus,
    retry_delay_seconds,
    run_delivery_cycle,
)


def _lease(*, attempts: int = 1, maximum: int = 5) -> DeliveryLease:
    return DeliveryLease(
        message=ExternalDeliveryMessage(
            delivery_id="delivery-1",
            notification_id="notification-1",
            idempotency_key="event-1:user-1:push",
            channel=DeliveryChannel.PUSH,
            destination="installation-1",
            title="Ignored for push",
            body="Ignored for push",
        ),
        provider_name="fake",
        attempts=attempts,
        max_attempts=maximum,
    )


@dataclass
class _Repository:
    lease: DeliveryLease
    revalidation_status: RevalidationStatus = RevalidationStatus.READY
    events: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

    def claim_batch(self, **kwargs):
        self.events.append("claim_committed")
        return [
            DeliveryClaim(
                delivery_id=self.lease.message.delivery_id,
                attempts=self.lease.attempts,
                max_attempts=self.lease.max_attempts,
            )
        ]

    def revalidate(self, **kwargs):
        self.events.append("revalidated")
        return Revalidation(
            self.revalidation_status,
            self.lease if self.revalidation_status is RevalidationStatus.READY else None,
        )

    def mark_delivered(self, **kwargs):
        self.events.append("delivered_committed")
        return True

    def mark_failed(self, **kwargs):
        self.events.append("failure_committed")
        self.failed.append(kwargs)
        return True


class _Provider:
    provider_name = "fake"

    def __init__(self, repository, result):
        self.repository = repository
        self.result = result

    def deliver(self, message):
        assert self.repository.events == ["claim_committed", "revalidated"]
        self.repository.events.append("external_io")
        return self.result


def test_worker_delivers_after_claim_commit_and_preference_revalidation():
    repository = _Repository(_lease())
    provider = _Provider(
        repository,
        IntegrationResult.succeeded(
            provider="fake",
            operation="deliver",
            value=DeliveryAcknowledgement("external-1"),
        ),
    )

    stats = run_delivery_cycle(
        repository,
        worker_id="worker-1",
        provider_resolver=lambda name, message: provider,
    )

    assert stats == {
        "claimed": 1,
        "delivered": 1,
        "retried": 0,
        "dead_lettered": 0,
        "suppressed": 0,
        "claim_lost": 0,
        "deferred": 0,
    }
    assert repository.events == [
        "claim_committed",
        "revalidated",
        "external_io",
        "delivered_committed",
    ]


def test_worker_suppresses_disabled_preference_without_provider_io():
    repository = _Repository(
        _lease(),
        revalidation_status=RevalidationStatus.SUPPRESSED,
    )

    stats = run_delivery_cycle(
        repository,
        worker_id="worker-1",
        provider_resolver=lambda *args: (_ for _ in ()).throw(AssertionError()),
    )

    assert stats["suppressed"] == 1
    assert repository.events == ["claim_committed", "revalidated"]


def test_worker_retries_transient_failure_with_provider_retry_after():
    repository = _Repository(_lease(attempts=2))
    failure = IntegrationFailure(
        code="provider_busy",
        message="provider is temporarily unavailable",
        retryable=True,
        retry_after_seconds=180,
    )
    provider = _Provider(
        repository,
        IntegrationResult.failed(
            provider="fake",
            operation="deliver",
            failure=failure,
        ),
    )
    now = datetime(2026, 9, 10, 12, 0, 0)

    stats = run_delivery_cycle(
        repository,
        worker_id="worker-1",
        provider_resolver=lambda name, message: provider,
        retry_base_seconds=30,
        clock=lambda: now,
    )

    assert stats["retried"] == 1
    recorded = repository.failed[0]
    assert recorded["terminal"] is False
    assert (recorded["retry_at"] - now).total_seconds() == 180


def test_worker_dead_letters_terminal_or_exhausted_failure():
    repository = _Repository(_lease(attempts=5, maximum=5))
    provider = _Provider(
        repository,
        IntegrationResult.failed(
            provider="fake",
            operation="deliver",
            failure=IntegrationFailure(
                code="provider_busy",
                message="provider is temporarily unavailable",
                retryable=True,
            ),
        ),
    )

    stats = run_delivery_cycle(
        repository,
        worker_id="worker-1",
        provider_resolver=lambda name, message: provider,
    )

    assert stats["dead_lettered"] == 1
    assert repository.failed[0]["terminal"] is True
    assert repository.failed[0]["retry_at"] is None


def test_worker_normalizes_provider_exception_without_secret_text():
    repository = _Repository(_lease())

    class Raising:
        def deliver(self, message):
            raise RuntimeError(f"Bearer raw-secret for {message.destination}")

    stats = run_delivery_cycle(
        repository,
        worker_id="worker-1",
        provider_resolver=lambda name, message: Raising(),
    )

    assert stats["retried"] == 1
    failure = repository.failed[0]["failure"]
    assert "raw-secret" not in failure.message
    assert "installation-1" not in failure.message


def test_exponential_backoff_is_bounded_and_honors_retry_after():
    assert retry_delay_seconds(attempts=1, base_seconds=30, maximum_seconds=300) == 30
    assert retry_delay_seconds(attempts=8, base_seconds=30, maximum_seconds=300) == 300
    assert (
        retry_delay_seconds(
            attempts=2,
            base_seconds=30,
            maximum_seconds=300,
            requested_seconds=240,
        )
        == 240
    )
