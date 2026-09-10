from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import Base
from app.models import (
    Company,
    Notification,
    NotificationDelivery,
    NotificationEndpoint,
    NotificationEventLink,
    NotificationPreference,
    OperationalDomainEvent,
    User,
)


def _id() -> str:
    return str(uuid.uuid4())


def _notification(*, company_id: str, user_id: str, suffix: str) -> Notification:
    return Notification(
        organization_id=company_id,
        recipient_user_id=user_id,
        recipient_kind="USER",
        recipient_key=f"user:{user_id}",
        category="REPORT",
        notification_type="report.published",
        title="Your results are ready",
        body="Open the verified report.",
        severity="INFO",
        target_type="REPORT",
        target_id=f"report-{suffix}",
        correlation_id=f"correlation-{suffix}",
        deduplication_key=f"report.published:{suffix}",
    )


def test_notification_models_expose_typed_targets_and_no_raw_url_column():
    expected_tables = {
        "notifications",
        "notification_event_links",
        "notification_deliveries",
        "notification_preferences",
        "notification_endpoints",
    }
    assert expected_tables.issubset(Base.metadata.tables)

    notification_columns = set(Notification.__table__.columns.keys())
    assert {"target_type", "target_id", "recipient_kind", "recipient_key"}.issubset(
        notification_columns
    )
    assert "deep_link" not in notification_columns
    assert "url" not in notification_columns

    endpoint_columns = set(NotificationEndpoint.__table__.columns.keys())
    assert "handle_ciphertext" in endpoint_columns
    assert "handle_digest" in endpoint_columns
    assert "handle" not in endpoint_columns


def test_notification_ledger_persists_inbox_event_delivery_preference_and_endpoint(
    db_session,
):
    suffix = _id()
    user = User(
        email=f"notification-{suffix}@example.test",
        password_hash="not-used",
        role="client",
        is_active=True,
    )
    company = Company(name="Notification tenant", email=f"tenant-{suffix}@example.test")
    db_session.add_all([user, company])
    db_session.flush()

    event = OperationalDomainEvent(
        aggregate_type="report",
        aggregate_id=f"report-{suffix}",
        event_type="report.published",
        payload_json="{}",
        idempotency_key=f"event:{suffix}",
        correlation_id=f"correlation-{suffix}",
    )
    notification = _notification(company_id=company.id, user_id=user.id, suffix=suffix)
    endpoint_handle = f"push-handle-{suffix}"
    endpoint = NotificationEndpoint(
        user_id=user.id,
        organization_id=company.id,
        installation_id=f"install-{suffix}",
        platform="IOS",
        provider="fake-push",
        handle_ciphertext=f"ciphertext:{endpoint_handle}",
        handle_digest=hashlib.sha256(endpoint_handle.encode()).hexdigest(),
        encryption_key_id="primary",
    )
    preference = NotificationPreference(
        user_id=user.id,
        organization_id=company.id,
        scope_key=company.id,
        category="REPORT",
        minimum_severity="INFO",
    )
    db_session.add_all([event, notification, endpoint, preference])
    db_session.flush()

    link = NotificationEventLink(
        notification_id=notification.id,
        event_id=event.id,
        recipient_key=notification.recipient_key,
    )
    delivery = NotificationDelivery(
        notification_id=notification.id,
        endpoint_id=endpoint.id,
        channel="PUSH",
        provider="fake-push",
        idempotency_key=f"delivery:{suffix}",
    )
    db_session.add_all([link, delivery])
    db_session.commit()

    stored = db_session.get(Notification, notification.id)
    assert stored is not None
    assert (stored.target_type, stored.target_id) == ("REPORT", f"report-{suffix}")
    assert stored.occurrence_count == 1
    assert stored.read_at is None
    assert db_session.get(NotificationDelivery, delivery.id).status == "PENDING"
    assert db_session.get(NotificationEndpoint, endpoint.id).handle_ciphertext != endpoint_handle


def test_notification_typed_target_check_rejects_unbound_report(db_session):
    suffix = _id()
    user = User(
        email=f"target-{suffix}@example.test",
        password_hash="not-used",
        role="client",
        is_active=True,
    )
    company = Company(name="Target tenant", email=f"target-org-{suffix}@example.test")
    db_session.add_all([user, company])
    db_session.flush()

    invalid = _notification(company_id=company.id, user_id=user.id, suffix=suffix)
    invalid.target_id = None
    db_session.add(invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

def test_notification_delivery_requires_complete_encrypted_payload_metadata(db_session):
    suffix = _id()
    user = User(
        email=f"payload-{suffix}@example.test",
        password_hash="not-used",
        role="client",
        is_active=True,
    )
    company = Company(name="Payload tenant", email=f"payload-org-{suffix}@example.test")
    db_session.add_all([user, company])
    db_session.flush()
    notification = _notification(company_id=company.id, user_id=user.id, suffix=suffix)
    db_session.add(notification)
    db_session.flush()

    invalid = NotificationDelivery(
        notification_id=notification.id,
        channel="EMAIL",
        provider="fake-email",
        idempotency_key=f"delivery:{suffix}",
        payload_ciphertext="ciphertext-without-key-metadata",
    )
    db_session.add(invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
