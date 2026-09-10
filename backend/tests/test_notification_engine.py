from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import uuid

import pytest

from app.core.config import settings
from app.core.events import DomainEvent
from app.core.time import utc_now
from app.core.tokens import create_user_access_token
from app.models import (
    Account,
    AccountMember,
    Action,
    Asset,
    Company,
    CompanyUser,
    EventOutbox,
    Invitation,
    Notification,
    NotificationDelivery,
    NotificationEventLink,
    NotificationPreference,
    Order,
    Report,
    User,
)
from app.modules.identity.domain import AuthorizationContext
from app.modules.notifications.domain import NotificationError
from app.modules.notifications.inbox import visible_notifications
from app.modules.notifications.materializer import (
    materialize_notification_event,
    stage_invitation_notification,
)
from app.modules.notifications.security import resolve_notification_target
from app.services.event_consumers import default_event_consumers
from app.services.event_outbox import (
    deliver_to_local_consumers,
    enqueue_domain_event,
    event_from_row,
)


def _id() -> str:
    return str(uuid.uuid4())


def _scope(db_session, prefix: str = "notification"):
    organization = Company(
        id=_id(),
        name=f"{prefix} organization",
        email=f"{prefix}-{_id()}@example.test",
        country="Angola",
        status="active",
    )
    workspace = Account(
        id=_id(),
        organization_id=organization.id,
        name=f"{prefix} workspace",
        sector_focus="agro",
        entity_type="business",
        customer_type="business",
    )
    user = User(
        id=_id(),
        email=f"{prefix}-{_id()}@example.test",
        role="cliente",
        is_active=True,
    )
    db_session.add_all((organization, workspace, user))
    db_session.flush()
    db_session.add_all(
        (
            CompanyUser(
                id=_id(),
                company_id=organization.id,
                user_id=user.id,
                email=user.email,
                role="viewer",
                is_active=True,
                status="active",
            ),
            AccountMember(
                account_id=workspace.id,
                user_id=user.id,
                role="viewer",
                status="active",
            ),
        )
    )
    db_session.flush()
    asset = Asset(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        sector="AGRICULTURE",
        asset_type="FIELD",
        name=f"{prefix} asset",
        status="active",
        metadata_json="{}",
        created_by_user_id=user.id,
        updated_by_user_id=user.id,
    )
    db_session.add(asset)
    db_session.flush()
    return organization, workspace, user, asset


def _context(user: User, organization: Company, workspace: Account):
    return AuthorizationContext(
        user_id=user.id,
        identity_subject=f"internal:{user.id}",
        active_organization_id=organization.id,
        active_workspace_id=workspace.id,
        organization_role="viewer",
        workspace_role="viewer",
        permissions=frozenset(
            {"profile:read", "organization:read", "workspace:read", "asset:read", "report:read"}
        ),
    )


def _report(db_session, organization, workspace, user, asset) -> Report:
    now = utc_now()
    row = Report(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        report_type="ASSET_INTELLIGENCE",
        title="Validated field report",
        template_version="1.0.0",
        revision=1,
        status="PUBLISHED",
        qa_level="AUTO_APPROVED",
        context_schema_version="geovision.report-context.v1",
        context_json="{}",
        context_sha256="a" * 64,
        narrative_provider="deterministic",
        narrative_schema_version="geovision.report-narrative.v1",
        narrative_json="{}",
        qa_result_json="{}",
        generation_key=f"test:{_id()}",
        generated_at=now,
        approved_at=now,
        published_at=now,
        created_by_user_id=user.id,
        lifecycle_version=1,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _event(db_session, *, name: str, aggregate_type: str, aggregate_id: str, payload: dict, at=None):
    row = enqueue_domain_event(
        db_session,
        name=name,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        idempotency_key=f"notification-test:{_id()}",
        occurred_at=at,
    )
    db_session.flush()
    return event_from_row(row)


def test_published_report_materializes_once_and_target_is_reauthorized(db_session):
    organization, workspace, user, asset = _scope(db_session, "report-ready")
    report = _report(db_session, organization, workspace, user, asset)
    event = _event(
        db_session,
        name="report.published",
        aggregate_type="report",
        aggregate_id=report.id,
        payload={
            "report_id": report.id,
            "organization_id": organization.id,
            "workspace_id": workspace.id,
            "asset_id": asset.id,
        },
    )

    first = materialize_notification_event(db_session, event)
    second = materialize_notification_event(db_session, event)
    db_session.commit()

    assert first.created == 1
    assert second.created == 0
    assert db_session.query(Notification).filter(
        Notification.recipient_user_id == user.id,
        Notification.notification_type == "report.results_ready",
    ).count() == 1
    notification = db_session.get(Notification, first.notification_ids[0])
    assert notification.title == "Your results are ready"
    assert db_session.query(NotificationEventLink).filter_by(
        notification_id=notification.id
    ).count() == 1
    assert db_session.query(NotificationDelivery).filter_by(
        notification_id=notification.id, channel="EMAIL"
    ).count() == 1

    resolved = resolve_notification_target(
        db_session,
        context=_context(user, organization, workspace),
        notification=notification,
    )
    assert resolved.target_id == report.id
    assert resolved.app_path == f"/reports/{report.id}"

    report.status = "SUPERSEDED"
    db_session.flush()
    with pytest.raises(NotificationError, match="not found"):
        resolve_notification_target(
            db_session,
            context=_context(user, organization, workspace),
            notification=notification,
        )


def test_default_event_consumer_materializes_with_its_runtime_delivery_config(db_session):
    organization, workspace, user, asset = _scope(db_session, "event-consumer")
    report = _report(db_session, organization, workspace, user, asset)
    event = _event(
        db_session,
        name="report.published",
        aggregate_type="report",
        aggregate_id=report.id,
        payload={"report_id": report.id},
    )
    config = settings.model_copy(update={"notification_provider": "disabled"})

    processed, duplicates = deliver_to_local_consumers(
        db_session,
        event,
        default_event_consumers(config),
    )
    db_session.commit()

    assert (processed, duplicates) == (1, 0)
    notification = db_session.query(Notification).filter_by(
        recipient_user_id=user.id,
        notification_type="report.results_ready",
    ).one()
    delivery = db_session.query(NotificationDelivery).filter_by(
        notification_id=notification.id,
        channel="EMAIL",
    ).one()
    assert delivery.provider == "disabled"
    assert delivery.status == "SUPPRESSED"


def test_customer_order_notification_does_not_fall_back_to_other_members(db_session):
    organization, workspace, owner, _ = _scope(db_session, "private-order")
    other = User(
        id=_id(),
        email=f"other-{_id()}@example.test",
        role="cliente",
        is_active=True,
    )
    db_session.add(other)
    db_session.flush()
    db_session.add_all(
        (
            CompanyUser(
                id=_id(),
                company_id=organization.id,
                user_id=other.id,
                email=other.email,
                role="viewer",
                is_active=True,
                status="active",
            ),
            AccountMember(
                account_id=workspace.id,
                user_id=other.id,
                role="viewer",
                status="active",
            ),
        )
    )
    order = Order(
        id=_id(),
        user_id=owner.id,
        organization_id=organization.id,
        workspace_id=workspace.id,
        order_type="SERVICE",
        fulfilment_status="CONFIRMED",
        payment_status="PAID",
        status="confirmed",
        currency="AOA",
    )
    db_session.add(order)
    db_session.flush()
    event = _event(
        db_session,
        name="order.created",
        aggregate_type="order",
        aggregate_id=order.id,
        payload={"order_id": order.id, "customer_visible": True},
    )

    result = materialize_notification_event(db_session, event)
    db_session.commit()

    assert result.created == 1
    recipients = {
        row.recipient_user_id
        for row in db_session.query(Notification).filter_by(
            target_type="ORDER",
            target_id=order.id,
        )
    }
    assert recipients == {owner.id}


def test_repeated_critical_action_events_are_aggregated_without_delivery_spam(db_session):
    organization, workspace, user, asset = _scope(db_session, "action-rate")
    action = Action(
        id=_id(),
        organization_id=organization.id,
        workspace_id=workspace.id,
        asset_id=asset.id,
        source_rule_key="agriculture.stress",
        source_rule_version="1.0.0",
        priority="CRITICAL",
        title="Inspect crop stress",
        description="Review the affected zone.",
        status="OPEN",
        recommendation_refs_json="[]",
        outcome_json="{}",
        deduplication_key=f"test:{_id()}",
        created_by_user_id=user.id,
    )
    db_session.add(action)
    db_session.flush()
    at = datetime(2026, 9, 10, 12, 0, 0)
    events = [
        _event(
            db_session,
            name="action.requested",
            aggregate_type="intelligence_action",
            aggregate_id=action.id,
            payload={"action_id": action.id},
            at=at + timedelta(minutes=index),
        )
        for index in (0, 2)
    ]

    first = materialize_notification_event(db_session, events[0])
    second = materialize_notification_event(db_session, events[1])
    db_session.commit()

    assert first.created == 1
    assert second.aggregated == 1
    notification = db_session.get(Notification, first.notification_ids[0])
    assert notification.occurrence_count == 2
    assert notification.severity == "CRITICAL"
    assert db_session.query(NotificationEventLink).filter_by(
        notification_id=notification.id
    ).count() == 2
    assert db_session.query(NotificationDelivery).filter_by(
        notification_id=notification.id
    ).count() == 1


def test_preferences_suppress_channels_and_inbox_visibility_without_losing_history(db_session):
    organization, workspace, user, asset = _scope(db_session, "preference")
    report = _report(db_session, organization, workspace, user, asset)
    db_session.add(
        NotificationPreference(
            id=_id(),
            user_id=user.id,
            organization_id=organization.id,
            scope_key=organization.id,
            category="REPORT",
            in_app_enabled=False,
            push_enabled=False,
            email_enabled=False,
            sms_enabled=False,
            minimum_severity="CRITICAL",
            timezone="UTC",
        )
    )
    event = _event(
        db_session,
        name="report.published",
        aggregate_type="report",
        aggregate_id=report.id,
        payload={"report_id": report.id},
    )

    result = materialize_notification_event(db_session, event)
    db_session.commit()

    notification = db_session.get(Notification, result.notification_ids[0])
    delivery = db_session.query(NotificationDelivery).filter_by(
        notification_id=notification.id
    ).one()
    assert delivery.status == "SUPPRESSED"
    rows, total, unread = visible_notifications(
        db_session,
        context=_context(user, organization, workspace),
    )
    assert notification not in rows
    assert total == unread == 0
    assert db_session.get(Notification, notification.id) is not None


def test_unencrypted_invitation_token_is_never_persisted(db_session):
    organization, workspace, owner, _ = _scope(db_session, "secure-invite")
    pending = CompanyUser(
        id=_id(),
        company_id=organization.id,
        user_id=None,
        email=f"invite-{_id()}@example.test",
        role="viewer",
        is_active=False,
        status="invited",
    )
    db_session.add(pending)
    db_session.flush()
    raw_token = f"raw-secret-{_id()}"
    invitation = Invitation(
        id=_id(),
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        token_prefix=raw_token[:8],
        organization_id=organization.id,
        workspace_id=workspace.id,
        membership_id=pending.id,
        target_email=pending.email,
        pending_email_key=pending.email,
        intended_role="viewer",
        target_type="workspace",
        target_id=workspace.id,
        metadata_json="{}",
        status="pending",
        invited_by_user_id=owner.id,
        expires_at=utc_now() + timedelta(hours=24),
    )
    db_session.add(invitation)
    db_session.flush()
    stage_invitation_notification(
        db_session,
        invitation=invitation,
        accept_url=f"https://portal.test/onboarding#{raw_token}",
        mobile_deep_link=f"geovision://invitation#{raw_token}",
    )
    db_session.commit()

    delivery = db_session.query(NotificationDelivery).join(Notification).filter(
        Notification.target_id == invitation.id
    ).one()
    assert delivery.status == "SUPPRESSED"
    assert delivery.payload_ciphertext is None
    stored = "\n".join(
        str(value or "")
        for value in (
            db_session.get(Notification, delivery.notification_id).body,
            delivery.payload_ciphertext,
            db_session.query(EventOutbox).filter_by(aggregate_id=invitation.id).one().payload_json,
        )
    )
    assert raw_token not in stored


def test_notification_api_is_recipient_bound_and_returns_typed_target(client, db_session):
    organization, workspace, user, asset = _scope(db_session, "notification-api")
    other = User(
        id=_id(),
        email=f"other-{_id()}@example.test",
        role="cliente",
        is_active=True,
    )
    db_session.add(other)
    report = _report(db_session, organization, workspace, user, asset)
    event = _event(
        db_session,
        name="report.published",
        aggregate_type="report",
        aggregate_id=report.id,
        payload={"report_id": report.id},
    )
    result = materialize_notification_event(db_session, event)
    db_session.commit()
    notification_id = result.notification_ids[0]

    def headers(subject: User):
        token = create_user_access_token(
            user_id=subject.id,
            email=subject.email,
            role=subject.role,
            auth_generation=subject.auth_generation,
        )
        return {
            "Authorization": f"Bearer {token}",
            "X-Workspace-ID": workspace.id,
        }

    inbox = client.get("/notifications", headers=headers(user))
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["items"][0]["id"] == notification_id
    target = client.get(
        f"/notifications/{notification_id}/target", headers=headers(user)
    )
    assert target.status_code == 200, target.text
    assert target.json()["app_path"] == f"/reports/{report.id}"

    hidden = client.get(
        f"/notifications/{notification_id}/target", headers=headers(other)
    )
    assert hidden.status_code in {403, 404}
