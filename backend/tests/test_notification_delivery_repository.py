"""Persistence and policy checks for the durable notification delivery worker."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import uuid

from app.database import SessionLocal
from app.models import (
    Company,
    CompanyUser,
    Notification,
    NotificationDelivery,
    NotificationEndpoint,
    NotificationPreference,
    User,
)
from app.workers.notification_delivery_repository import (
    SqlAlchemyNotificationDeliveryRepository,
)
from app.workers.notification_delivery_runner import RevalidationStatus


def _id() -> str:
    return str(uuid.uuid4())


def _seed_user_delivery(db, *, channel: str = "PUSH") -> tuple[str, str, str]:
    organization_id = _id()
    user_id = _id()
    notification_id = _id()
    delivery_id = _id()
    endpoint_id = _id() if channel == "PUSH" else None
    email = f"customer-{user_id}@example.com"
    db.add(
        Company(
            id=organization_id,
            name="Delivery Test Organization",
            email=f"org-{organization_id}@example.com",
            country="Angola",
        )
    )
    db.add(User(id=user_id, email=email, role="client", is_active=True))
    db.add(
        CompanyUser(
            id=_id(),
            company_id=organization_id,
            user_id=user_id,
            email=email,
            role="viewer",
            status="active",
            is_active=True,
        )
    )
    db.add(
        Notification(
            id=notification_id,
            organization_id=organization_id,
            recipient_user_id=user_id,
            recipient_kind="USER",
            recipient_key=f"user:{user_id}",
            category="REPORT",
            notification_type="report.published",
            title="Your results are ready",
            body="Open GeoVision to review the published report.",
            severity="INFO",
            target_type="REPORT",
            target_id=_id(),
            deduplication_key=f"report:{notification_id}",
        )
    )
    if endpoint_id:
        db.add(
            NotificationEndpoint(
                id=endpoint_id,
                user_id=user_id,
                organization_id=organization_id,
                installation_id=f"installation-{endpoint_id}",
                platform="IOS",
                provider="azure_notification_hubs",
                handle_ciphertext=endpoint_id,
                handle_digest=hashlib.sha256(endpoint_id.encode()).hexdigest(),
                encryption_key_id="primary",
                status="ACTIVE",
            )
        )
    db.add(
        NotificationDelivery(
            id=delivery_id,
            notification_id=notification_id,
            endpoint_id=endpoint_id,
            channel=channel,
            provider=("azure_notification_hubs" if channel == "PUSH" else "smtp"),
            status="PENDING",
            idempotency_key=f"notification:{notification_id}:{channel.lower()}",
        )
    )
    db.commit()
    return delivery_id, user_id, organization_id


def _repository(decoder=lambda value: value):
    return SqlAlchemyNotificationDeliveryRepository(
        SessionLocal,
        payload_decoder=decoder,
    )


def test_repository_claims_then_revalidates_active_push_endpoint(db_session):
    delivery_id, _, _ = _seed_user_delivery(db_session)
    now = datetime(2026, 9, 10, 12, 0, 0)
    repository = _repository()

    claims = repository.claim_batch(
        worker_id="worker-1",
        now=now,
        batch_size=10,
        lease_seconds=300,
    )
    checked = repository.revalidate(
        worker_id="worker-1",
        delivery_id=delivery_id,
        now=now,
    )

    assert delivery_id in [claim.delivery_id for claim in claims]
    assert checked.status is RevalidationStatus.READY
    assert checked.lease.message.destination.startswith("installation-")
    assert checked.lease.message.notification_id
    assert checked.lease.message.platform == "IOS"
    assert checked.lease.message.provider_handle
    assert checked.lease.message.provider_handle not in repr(checked.lease.message)
    assert "REPORT" not in checked.lease.message.destination


def test_repository_rechecks_preference_and_suppresses_before_delivery(db_session):
    delivery_id, user_id, organization_id = _seed_user_delivery(db_session)
    db_session.add(
        NotificationPreference(
            id=_id(),
            user_id=user_id,
            organization_id=organization_id,
            scope_key=organization_id,
            category="REPORT",
            push_enabled=False,
            email_enabled=True,
            in_app_enabled=True,
            minimum_severity="INFO",
            timezone="UTC",
        )
    )
    db_session.commit()
    now = datetime(2026, 9, 10, 12, 0, 0)
    repository = _repository()
    repository.claim_batch(
        worker_id="worker-1", now=now, batch_size=10, lease_seconds=300
    )

    checked = repository.revalidate(
        worker_id="worker-1", delivery_id=delivery_id, now=now
    )

    assert checked.status is RevalidationStatus.SUPPRESSED
    db_session.expire_all()
    row = db_session.get(NotificationDelivery, delivery_id)
    assert row.status == "SUPPRESSED"
    assert row.claimed_by is None


def test_repository_defers_quiet_hours_without_consuming_an_attempt(db_session):
    delivery_id, user_id, organization_id = _seed_user_delivery(db_session)
    db_session.add(
        NotificationPreference(
            id=_id(),
            user_id=user_id,
            organization_id=organization_id,
            scope_key=organization_id,
            category="REPORT",
            push_enabled=True,
            email_enabled=True,
            in_app_enabled=True,
            minimum_severity="INFO",
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            timezone="UTC",
        )
    )
    db_session.commit()
    now = datetime(2026, 9, 10, 23, 30, 0)
    repository = _repository()
    repository.claim_batch(
        worker_id="worker-1", now=now, batch_size=10, lease_seconds=300
    )

    checked = repository.revalidate(
        worker_id="worker-1", delivery_id=delivery_id, now=now
    )

    assert checked.status is RevalidationStatus.DEFERRED
    db_session.expire_all()
    row = db_session.get(NotificationDelivery, delivery_id)
    assert row.status == "RETRY"
    assert row.attempts == 0
    assert row.next_attempt_at == datetime(2026, 9, 11, 7, 0, 0)


def test_repository_decrypts_and_hash_checks_pre_account_email(db_session):
    organization_id = _id()
    notification_id = _id()
    delivery_id = _id()
    db_session.add(
        Company(
            id=organization_id,
            name="Invitation Organization",
            email=f"org-{organization_id}@example.com",
            country="Angola",
        )
    )
    db_session.add(
        Notification(
            id=notification_id,
            organization_id=organization_id,
            recipient_user_id=None,
            recipient_kind="PRE_ACCOUNT",
            recipient_key=f"invitation:{notification_id}",
            category="INVITATION",
            notification_type="invitation.created",
            title="Invitation",
            body="Invitation staged securely.",
            severity="INFO",
            target_type="INVITATION",
            target_id=_id(),
            deduplication_key=f"invitation:{notification_id}",
        )
    )
    plaintext = json.dumps(
        {
            "destination": "invitee@example.com",
            "title": "You are invited",
            "body": "Open the one-time invitation link.",
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    db_session.add(
        NotificationDelivery(
            id=delivery_id,
            notification_id=notification_id,
            channel="EMAIL",
            provider="smtp",
            status="PENDING",
            idempotency_key=f"notification:{notification_id}:email",
            payload_ciphertext="opaque-ciphertext",
            payload_key_id="primary",
            payload_sha256=hashlib.sha256(plaintext.encode()).hexdigest(),
        )
    )
    db_session.commit()
    now = datetime(2026, 9, 10, 12, 0, 0)
    repository = _repository(lambda value: plaintext)
    repository.claim_batch(
        worker_id="worker-1", now=now, batch_size=10, lease_seconds=300
    )

    checked = repository.revalidate(
        worker_id="worker-1", delivery_id=delivery_id, now=now
    )

    assert checked.status is RevalidationStatus.READY
    assert checked.lease.message.destination == "invitee@example.com"
    assert "invitee@example.com" not in repr(checked.lease.message)


def test_repository_dead_letters_tampered_encrypted_payload(db_session):
    delivery_id, _, _ = _seed_user_delivery(db_session, channel="EMAIL")
    row = db_session.get(NotificationDelivery, delivery_id)
    row.payload_ciphertext = "opaque-ciphertext"
    row.payload_key_id = "primary"
    row.payload_sha256 = "0" * 64
    db_session.commit()
    now = datetime(2026, 9, 10, 12, 0, 0)
    repository = _repository(lambda value: '{"destination":"private@example.com"}')
    repository.claim_batch(
        worker_id="worker-1", now=now, batch_size=10, lease_seconds=300
    )

    checked = repository.revalidate(
        worker_id="worker-1", delivery_id=delivery_id, now=now
    )

    assert checked.status is RevalidationStatus.DEAD_LETTERED
    db_session.expire_all()
    row = db_session.get(NotificationDelivery, delivery_id)
    assert row.status == "DEAD_LETTER"
    assert row.last_error_message == "notification delivery data is invalid"
    assert "private@example.com" not in row.last_error_message


def test_repository_dead_letters_plaintext_push_endpoint(db_session):
    delivery_id, _, _ = _seed_user_delivery(db_session)
    delivery = db_session.get(NotificationDelivery, delivery_id)
    endpoint = db_session.get(NotificationEndpoint, delivery.endpoint_id)
    endpoint.handle_ciphertext = "plain:must-not-be-used"
    endpoint.handle_digest = hashlib.sha256(b"must-not-be-used").hexdigest()
    db_session.commit()
    now = datetime(2026, 9, 10, 12, 0, 0)
    repository = _repository()
    repository.claim_batch(
        worker_id="worker-1", now=now, batch_size=10, lease_seconds=300
    )

    checked = repository.revalidate(
        worker_id="worker-1", delivery_id=delivery_id, now=now
    )

    assert checked.status is RevalidationStatus.DEAD_LETTERED
    db_session.expire_all()
    row = db_session.get(NotificationDelivery, delivery_id)
    assert row.status == "DEAD_LETTER"
    assert "must-not-be-used" not in row.last_error_message


def test_repository_recovers_stale_claim_and_dead_letters_when_exhausted(db_session):
    delivery_id, _, _ = _seed_user_delivery(db_session)
    row = db_session.get(NotificationDelivery, delivery_id)
    row.status = "PROCESSING"
    row.claimed_by = "dead-worker"
    row.claimed_at = datetime(2026, 9, 10, 10, 0, 0)
    row.lease_expires_at = datetime(2026, 9, 10, 10, 5, 0)
    row.attempts = row.max_attempts
    db_session.commit()

    claims = _repository().claim_batch(
        worker_id="worker-2",
        now=datetime(2026, 9, 10, 12, 0, 0),
        batch_size=10,
        lease_seconds=300,
    )

    assert all(claim.delivery_id != delivery_id for claim in claims)
    db_session.expire_all()
    row = db_session.get(NotificationDelivery, delivery_id)
    assert row.status == "DEAD_LETTER"
    assert row.claimed_by is None
