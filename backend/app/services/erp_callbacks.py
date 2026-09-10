"""Authenticated Odoo callback handling and non-authoritative status projection."""

from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import ErpCallbackReceipt, ErpExternalReference


class ErpCallbackError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.safe_message = message
        self.status_code = status_code
        super().__init__(message)


def verify_callback_signature(
    raw_body: bytes,
    *,
    timestamp: str,
    signature: str,
    secret: str | None,
    replay_window_seconds: int,
    now_seconds: float | None = None,
) -> None:
    if not secret:
        raise ErpCallbackError(
            "odoo_callback_not_configured",
            "Odoo callback authentication is not configured",
            status_code=503,
        )
    try:
        signed_at = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise ErpCallbackError(
            "odoo_callback_timestamp_invalid",
            "Odoo callback timestamp is invalid",
            status_code=401,
        ) from exc
    current = time.time() if now_seconds is None else now_seconds
    if abs(current - signed_at) > replay_window_seconds:
        raise ErpCallbackError(
            "odoo_callback_expired",
            "Odoo callback timestamp is outside the replay window",
            status_code=401,
        )
    if not signature.startswith("sha256="):
        raise ErpCallbackError(
            "odoo_callback_signature_invalid",
            "Odoo callback signature is invalid",
            status_code=401,
        )
    supplied = signature[len("sha256=") :].strip().lower()
    if len(supplied) != 64:
        raise ErpCallbackError(
            "odoo_callback_signature_invalid",
            "Odoo callback signature is invalid",
            status_code=401,
        )
    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise ErpCallbackError(
            "odoo_callback_signature_invalid",
            "Odoo callback signature is invalid",
            status_code=401,
        )


def apply_odoo_status_callback(
    db: Session,
    *,
    payload: dict[str, Any],
    payload_sha256: str,
) -> tuple[str, ErpExternalReference]:
    """Apply status fields to the ERP projection, never to the core order."""

    event_id = str(payload["event_id"])
    existing_receipt = (
        db.query(ErpCallbackReceipt)
        .filter(
            ErpCallbackReceipt.provider == "odoo",
            ErpCallbackReceipt.event_id == event_id,
        )
        .one_or_none()
    )
    if existing_receipt is not None:
        if not hmac.compare_digest(existing_receipt.payload_sha256, payload_sha256):
            raise ErpCallbackError(
                "odoo_callback_event_collision",
                "Odoo callback event ID was already used with different content",
                status_code=409,
            )
        reference = (
            db.query(ErpExternalReference)
            .filter(
                ErpExternalReference.provider == "odoo",
                ErpExternalReference.resource_type == str(payload["resource_type"]),
                ErpExternalReference.internal_id == str(payload["geovision_id"]),
            )
            .one_or_none()
        )
        if reference is None:
            raise ErpCallbackError(
                "odoo_reference_missing",
                "Odoo callback has no GeoVision mapping",
                status_code=404,
            )
        return "duplicate", reference

    reference = (
        db.query(ErpExternalReference)
        .filter(
            ErpExternalReference.provider == "odoo",
            ErpExternalReference.resource_type == str(payload["resource_type"]),
            ErpExternalReference.internal_id == str(payload["geovision_id"]),
        )
        .one_or_none()
    )
    if reference is None:
        raise ErpCallbackError(
            "odoo_reference_missing",
            "Odoo callback has no GeoVision mapping",
            status_code=404,
        )
    if not hmac.compare_digest(reference.external_id, str(payload["external_id"])):
        raise ErpCallbackError(
            "odoo_reference_mismatch",
            "Odoo callback external reference does not match GeoVision",
            status_code=409,
        )
    callback_model = payload.get("external_model")
    if (
        callback_model
        and reference.external_model
        and not hmac.compare_digest(reference.external_model, str(callback_model))
    ):
        raise ErpCallbackError(
            "odoo_model_mismatch",
            "Odoo callback external model does not match GeoVision",
            status_code=409,
        )

    now = utc_now()
    for field_name in ("invoice_status", "stock_status", "purchase_status"):
        if payload.get(field_name) is not None:
            setattr(reference, field_name, str(payload[field_name])[:100])
    provider_updated_at = payload.get("provider_updated_at")
    if isinstance(provider_updated_at, datetime):
        reference.provider_updated_at = provider_updated_at.replace(tzinfo=None)
    reference.last_callback_at = now
    reference.updated_at = now
    receipt = ErpCallbackReceipt(
        provider="odoo",
        event_id=event_id,
        payload_sha256=payload_sha256,
        signature_verified=True,
        resource_type=reference.resource_type,
        internal_id=reference.internal_id,
        external_id=reference.external_id,
        outcome="PROCESSED",
        received_at=now,
        processed_at=now,
    )
    db.add(receipt)
    db.flush()
    return "processed", reference


__all__ = [
    "ErpCallbackError",
    "apply_odoo_status_callback",
    "verify_callback_signature",
]
