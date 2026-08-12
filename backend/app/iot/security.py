from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone

from app.config import settings
from app.crypto import decrypt, encrypt
from app.time_utils import utc_now


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secret_matches(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(value), expected_hash)


def protect_secret(value: str) -> str:
    protected = encrypt(value)
    if not protected:
        raise RuntimeError("Unable to protect device secret")
    return protected


def reveal_secret(value: str) -> str:
    revealed = decrypt(value)
    if not revealed:
        raise RuntimeError("Unable to decrypt device secret")
    return revealed


def canonical_mqtt_payload(payload: dict) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_mqtt_payload(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_mqtt_payload(payload), hashlib.sha256).hexdigest()


def verify_mqtt_signature(payload: dict, secret: str) -> bool:
    supplied = str(payload.get("signature") or "")
    expected = sign_mqtt_payload(payload, secret)
    return bool(supplied) and hmac.compare_digest(supplied, expected)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def timestamp_is_fresh(value: datetime) -> bool:
    delta = abs((utc_now() - value).total_seconds())
    return delta <= settings.iot_message_max_age_seconds
