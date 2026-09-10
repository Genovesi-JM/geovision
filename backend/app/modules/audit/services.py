"""Canonical, transaction-joining security audit writer."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.observability import current_context, safe_identifier, sanitize_fields
from app.models import AuditLog, User


_AUDIT_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{1,99}$")
_OUTCOMES = frozenset({"UNKNOWN", "SUCCESS", "FAILURE", "DENIED"})


def _stable_name(value: str, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _AUDIT_NAME.fullmatch(normalized):
        raise ValueError(f"{field} must be a stable lowercase identifier")
    return normalized


def _safe_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    sanitized = sanitize_fields(dict(details or {}))
    if not isinstance(sanitized, dict):
        return {}
    return {"schema_version": "geovision.audit.v1", **sanitized}


def audit_details(row: AuditLog) -> dict[str, Any]:
    """Decode legacy/current audit JSON without propagating malformed payloads."""

    try:
        value = json.loads(row.details or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def record_audit_event(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    actor: User | None = None,
    user_id: str | None = None,
    user_email: str | None = None,
    organization_id: str | None = None,
    workspace_id: str | None = None,
    outcome: str = "SUCCESS",
    details: Mapping[str, Any] | None = None,
    request: Request | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Stage one sanitized audit event in the caller's database transaction."""

    normalized_outcome = str(outcome or "UNKNOWN").strip().upper()
    if normalized_outcome not in _OUTCOMES:
        raise ValueError("outcome is not supported")
    context = current_context()
    resolved_user_id = actor.id if actor is not None else user_id
    resolved_user_email = actor.email if actor is not None else user_email
    resolved_organization_id = organization_id or context.get("organization_id")
    resolved_workspace_id = workspace_id or context.get("workspace_id")
    resolved_request_id = safe_identifier(
        request_id, fallback=safe_identifier(context.get("request_id"))
    )
    resolved_correlation_id = safe_identifier(
        correlation_id, fallback=safe_identifier(context.get("correlation_id"))
    )
    if request is not None:
        resolved_request_id = safe_identifier(
            getattr(request.state, "request_id", None), fallback=resolved_request_id
        )
        resolved_correlation_id = safe_identifier(
            getattr(request.state, "correlation_id", None),
            fallback=resolved_correlation_id,
        )
    entry = AuditLog(
        user_id=resolved_user_id,
        user_email=(str(resolved_user_email)[:320] if resolved_user_email else None),
        action=_stable_name(action, "action"),
        resource_type=_stable_name(resource_type, "resource_type"),
        resource_id=(str(resource_id)[:36] if resource_id else None),
        organization_id=(
            str(resolved_organization_id)[:36] if resolved_organization_id else None
        ),
        workspace_id=(
            str(resolved_workspace_id)[:36] if resolved_workspace_id else None
        ),
        request_id=resolved_request_id,
        correlation_id=resolved_correlation_id,
        outcome=normalized_outcome,
        details=json.dumps(
            _safe_details(details),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ),
        ip_address=(
            str(ip_address)[:45]
            if ip_address
            else (
                str(request.client.host)[:45]
                if request is not None and request.client is not None
                else None
            )
        ),
        user_agent=(
            str(user_agent)[:500]
            if user_agent
            else (
                str(request.headers.get("user-agent") or "")[:500]
                if request is not None
                else None
            )
        ),
    )
    db.add(entry)
    return entry


__all__ = ["audit_details", "record_audit_event"]
