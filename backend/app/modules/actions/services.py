"""Tenant-safe action generation, assignment, and outcome services."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.event_names import EventNames
from app.core.time import utc_now
from app.models import (
    AccountMember,
    Action,
    Asset,
    AuditLog,
    CatalogItem,
    CompanyUser,
    Observation,
    User,
)
from app.modules.actions.domain import (
    ActionError,
    ActionPriority,
    ActionStatus,
    require_action_transition,
)
from app.modules.analytics.domain import ActionRecommendation
from app.modules.analytics.services import EvaluationResult, PendingAction
from app.modules.datasets.domain import reject_sensitive_metadata
from app.services.event_outbox import enqueue_domain_event


def _json(value: Any, *, field_name: str) -> str:
    reject_sensitive_metadata(value, field_name)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ActionError("invalid_json", f"{field_name} must be JSON-compatible") from exc
    if len(encoded.encode("utf-8")) > 65_536:
        raise ActionError("payload_too_large", f"{field_name} must not exceed 64 KiB")
    return encoded


def _object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _array(value: str | None) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _audit(
    db: Session,
    *,
    actor: User | None,
    name: str,
    action: Action,
    details: Mapping[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id if actor else None,
            user_email=actor.email if actor else None,
            action=name,
            resource_type="intelligence_action",
            resource_id=action.id,
            details=_json(
                {
                    "organization_id": action.organization_id,
                    "workspace_id": action.workspace_id,
                    "asset_id": action.asset_id,
                    **dict(details or {}),
                },
                field_name="audit_details",
            ),
        )
    )


def _deduplication_key(
    *,
    asset_id: str,
    rule_key: str,
    rule_version: str,
    recommendation_key: str,
    observation_id: str | None,
) -> str:
    raw = ":".join(
        (asset_id, rule_key, rule_version, recommendation_key, observation_id or "none")
    )
    if len(raw) <= 240:
        return raw
    return f"sha256:{hashlib.sha256(raw.encode()).hexdigest()}"


def _validate_assignment(db: Session, asset: Asset, user_id: str | None) -> None:
    if not user_id:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ActionError("assignee_not_found", "Action assignee was not found")
    workspace_member = (
        db.query(AccountMember)
        .filter(
            AccountMember.account_id == asset.workspace_id,
            AccountMember.user_id == user_id,
            AccountMember.status == "active",
        )
        .first()
        if asset.workspace_id
        else None
    )
    organization_member = (
        db.query(CompanyUser)
        .filter(
            CompanyUser.company_id == asset.organization_id,
            CompanyUser.user_id == user_id,
            CompanyUser.status == "active",
            CompanyUser.is_active.is_(True),
        )
        .first()
    )
    if workspace_member is None and organization_member is None:
        raise ActionError("assignee_not_found", "Action assignee is not active in this workspace")


def _validate_catalogue(
    db: Session,
    asset: Asset,
    catalog_item_id: str | None,
) -> None:
    if not catalog_item_id:
        return
    item = db.get(CatalogItem, catalog_item_id)
    if item is None or item.status != "PUBLISHED":
        raise ActionError(
            "catalog_item_not_found", "Recommended GeoVision catalogue item is unavailable"
        )
    try:
        sectors = json.loads(item.sectors_json or "[]")
        asset_types = json.loads(item.asset_types_json or "[]")
    except (TypeError, ValueError):
        sectors, asset_types = [], []
    if sectors and asset.sector not in sectors:
        raise ActionError(
            "catalog_item_mismatch", "Recommended catalogue item does not support this sector"
        )
    if asset_types and asset.asset_type not in asset_types:
        raise ActionError(
            "catalog_item_mismatch", "Recommended catalogue item does not support this asset type"
        )


def create_action_from_recommendation(
    db: Session,
    *,
    asset: Asset,
    rule_key: str,
    rule_version: str,
    recommendation: ActionRecommendation,
    source_observation_id: str | None,
    actor: User | None = None,
) -> tuple[Action, bool]:
    try:
        priority = ActionPriority(recommendation.priority)
    except ValueError as exc:
        raise ActionError("invalid_priority", "Action priority is not supported") from exc
    source_observation = (
        db.get(Observation, source_observation_id) if source_observation_id else None
    )
    if source_observation_id and (
        source_observation is None
        or source_observation.organization_id != asset.organization_id
        or source_observation.asset_id != asset.id
    ):
        raise ActionError(
            "observation_not_found", "Source observation was not found for this asset"
        )
    _validate_assignment(db, asset, recommendation.assigned_to_user_id)
    _validate_catalogue(db, asset, recommendation.recommended_catalog_item_id)
    deduplication_key = _deduplication_key(
        asset_id=asset.id,
        rule_key=rule_key,
        rule_version=rule_version,
        recommendation_key=recommendation.key,
        observation_id=source_observation_id,
    )
    existing = (
        db.query(Action)
        .filter(
            Action.organization_id == asset.organization_id,
            Action.deduplication_key == deduplication_key,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing, False

    now = utc_now()
    row = Action(
        id=str(uuid.uuid4()),
        organization_id=asset.organization_id,
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        source_observation_id=source_observation_id,
        source_rule_key=rule_key,
        source_rule_version=rule_version,
        priority=priority.value,
        title=recommendation.title.strip()[:240],
        description=recommendation.description.strip(),
        status=ActionStatus.OPEN.value,
        due_date=_utc_naive(recommendation.due_date),
        assigned_to_user_id=recommendation.assigned_to_user_id,
        recommended_catalog_item_id=recommendation.recommended_catalog_item_id,
        recommendation_refs_json=_json(
            list(recommendation.recommendation_refs), field_name="recommendation_refs"
        ),
        outcome_json="{}",
        deduplication_key=deduplication_key,
        lifecycle_version=1,
        created_by_user_id=actor.id if actor else None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        actor=actor,
        name="intelligence_action.created",
        action=row,
        details={
            "rule": rule_key,
            "rule_version": rule_version,
            "source_observation_id": source_observation_id,
        },
    )
    enqueue_domain_event(
        db,
        name=EventNames.ACTION_REQUESTED,
        aggregate_type="intelligence_action",
        aggregate_id=row.id,
        idempotency_key=f"intelligence-action:{row.id}:requested",
        correlation_id=source_observation_id or asset.id,
        payload={
            "action_id": row.id,
            "organization_id": row.organization_id,
            "workspace_id": row.workspace_id,
            "asset_id": row.asset_id,
            "source_observation_id": row.source_observation_id,
            "priority": row.priority,
            "status": row.status,
            "source_rule": row.source_rule_key,
            "source_rule_version": row.source_rule_version,
            "recommended_catalog_item_id": row.recommended_catalog_item_id,
        },
    )
    return row, True


def materialize_evaluation_actions(
    db: Session,
    *,
    asset: Asset,
    evaluation: EvaluationResult,
    actor: User | None = None,
) -> tuple[Action, ...]:
    rows: list[Action] = []
    for item in evaluation.pending_actions:
        row, _ = create_action_from_recommendation(
            db,
            asset=asset,
            rule_key=item.rule_key,
            rule_version=item.rule_version,
            recommendation=item.recommendation,
            source_observation_id=item.source_observation_id,
            actor=actor,
        )
        rows.append(row)
    return tuple(rows)


def list_asset_actions(
    db: Session,
    *,
    asset: Asset,
    status: str | None = None,
    assigned_to_user_id: str | None = None,
    limit: int = 100,
) -> list[Action]:
    query = db.query(Action).filter(
        Action.organization_id == asset.organization_id,
        Action.asset_id == asset.id,
    )
    if asset.workspace_id:
        query = query.filter(Action.workspace_id == asset.workspace_id)
    if status:
        try:
            normalized_status = ActionStatus(status.upper()).value
        except ValueError as exc:
            raise ActionError("invalid_status", "Action status is not supported") from exc
        query = query.filter(Action.status == normalized_status)
    if assigned_to_user_id:
        query = query.filter(Action.assigned_to_user_id == assigned_to_user_id)
    priority_order = {
        "CRITICAL": 0,
        "URGENT": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4,
    }
    rows = query.order_by(Action.due_date, Action.created_at.desc()).limit(limit).all()
    return sorted(
        rows,
        key=lambda item: (
            item.status not in {"OPEN", "IN_PROGRESS"},
            priority_order.get(item.priority, 5),
            item.due_date or datetime.max,
            item.created_at,
        ),
    )


def get_asset_action(db: Session, *, asset: Asset, action_id: str) -> Action:
    row = db.get(Action, action_id)
    if (
        row is None
        or row.organization_id != asset.organization_id
        or row.asset_id != asset.id
        or (asset.workspace_id and row.workspace_id != asset.workspace_id)
    ):
        raise ActionError("action_not_found", "Action was not found")
    return row


def update_action_status(
    db: Session,
    *,
    action: Action,
    actor: User,
    target: str,
    expected_version: int,
    outcome: Mapping[str, Any] | None = None,
) -> Action:
    if action.lifecycle_version != expected_version:
        raise ActionError("version_conflict", "Action changed since it was last read")
    try:
        target_status = ActionStatus(target)
    except ValueError as exc:
        raise ActionError("invalid_status", "Action status is not supported") from exc
    previous = action.status
    require_action_transition(previous, target_status.value)
    if target_status is ActionStatus.COMPLETED and not outcome:
        raise ActionError("outcome_required", "Completed actions require a structured outcome")
    if target_status is not ActionStatus.COMPLETED and outcome:
        raise ActionError("invalid_outcome", "Outcome can only be recorded on completion")
    if previous == target_status.value:
        return action
    now = utc_now()
    action.status = target_status.value
    action.lifecycle_version += 1
    action.updated_at = now
    if target_status is ActionStatus.COMPLETED:
        action.outcome_json = _json(dict(outcome or {}), field_name="outcome")
        action.completed_at = now
        action.completed_by_user_id = actor.id
    else:
        action.completed_at = None
        action.completed_by_user_id = None
    _audit(
        db,
        actor=actor,
        name="intelligence_action.status_changed",
        action=action,
        details={"from": previous, "to": target_status.value},
    )
    event_name = (
        EventNames.ACTION_COMPLETED
        if target_status is ActionStatus.COMPLETED
        else EventNames.ACTION_REQUESTED
    )
    enqueue_domain_event(
        db,
        name=event_name,
        aggregate_type="intelligence_action",
        aggregate_id=action.id,
        idempotency_key=(
            f"intelligence-action:{action.id}:status:{action.lifecycle_version}:{target_status.value}"
        ),
        correlation_id=action.source_observation_id or action.asset_id,
        payload={
            "action_id": action.id,
            "organization_id": action.organization_id,
            "workspace_id": action.workspace_id,
            "asset_id": action.asset_id,
            "status": target_status.value,
            "previous_status": previous,
            "lifecycle_version": action.lifecycle_version,
        },
    )
    return action


def update_action_assignment(
    db: Session,
    *,
    asset: Asset,
    action: Action,
    actor: User,
    expected_version: int,
    assigned_to_user_id: str | None,
    due_date: datetime | None,
) -> Action:
    if action.lifecycle_version != expected_version:
        raise ActionError("version_conflict", "Action changed since it was last read")
    if action.status in {ActionStatus.COMPLETED.value, ActionStatus.CANCELLED.value}:
        raise ActionError("action_closed", "Closed actions cannot be reassigned")
    _validate_assignment(db, asset, assigned_to_user_id)
    previous_assignee = action.assigned_to_user_id
    action.assigned_to_user_id = assigned_to_user_id
    action.due_date = _utc_naive(due_date)
    action.lifecycle_version += 1
    action.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        name="intelligence_action.updated",
        action=action,
        details={
            "previous_assignee": previous_assignee,
            "assigned_to_user_id": assigned_to_user_id,
            "due_date": action.due_date.isoformat() if action.due_date else None,
        },
    )
    return action


def action_payload(row: Action) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "asset_id": row.asset_id,
        "source_observation_id": row.source_observation_id,
        "source_rule": row.source_rule_key,
        "source_rule_version": row.source_rule_version,
        "priority": row.priority,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "due_date": row.due_date,
        "assigned_to_user_id": row.assigned_to_user_id,
        "recommended_catalog_item_id": row.recommended_catalog_item_id,
        "recommendation_refs": _array(row.recommendation_refs_json),
        "outcome": _object(row.outcome_json),
        "lifecycle_version": row.lifecycle_version,
        "completed_by_user_id": row.completed_by_user_id,
        "completed_at": row.completed_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


__all__ = [
    "action_payload",
    "create_action_from_recommendation",
    "get_asset_action",
    "list_asset_actions",
    "materialize_evaluation_actions",
    "update_action_assignment",
    "update_action_status",
]
