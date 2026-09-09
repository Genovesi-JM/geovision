from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.core.integration import IntegrationStatus
from app.integrations.identity.entra_external_id import EntraExternalIdProvider
from app.integrations.identity.internal import InternalIdentityProvider
from app.modules.identity.domain import TokenUse


ISSUER = "https://geovision-test.ciamlogin.com/11111111-1111-4111-8111-111111111111/v2.0/"
AUDIENCE = "22222222-2222-4222-8222-222222222222"
TENANT_ID = "11111111-1111-4111-8111-111111111111"
OBJECT_ID = "33333333-3333-4333-8333-333333333333"
AUTHORIZED_PARTY = "44444444-4444-4444-8444-444444444444"
DISCOVERY_URL = ISSUER + ".well-known/openid-configuration"
JWKS_URL = "https://geovision-test.ciamlogin.com/discovery/v2.0/keys"


def _rsa_key_and_jwk(key_id: str):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    jwk.update({"kid": key_id, "use": "sig", "alg": "RS256", "issuer": ISSUER})
    return private_key, jwk


class FakeDocumentFetcher:
    def __init__(self, jwks_documents: list[dict[str, Any]]) -> None:
        self.jwks_documents = jwks_documents
        self.calls: list[str] = []
        self.fail_urls: set[str] = set()
        self.discovery = {"issuer": ISSUER, "jwks_uri": JWKS_URL}

    def fetch_json(
        self,
        url: str,
        *,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
    ) -> dict[str, Any]:
        assert connect_timeout_seconds == 2.0
        assert read_timeout_seconds == 7.0
        self.calls.append(url)
        if url in self.fail_urls:
            raise TimeoutError("sensitive upstream detail must not escape")
        if url == DISCOVERY_URL:
            return self.discovery
        if url == JWKS_URL:
            index = min(self.calls.count(JWKS_URL) - 1, len(self.jwks_documents) - 1)
            return self.jwks_documents[index]
        raise AssertionError("unexpected URL")


def _provider(fetcher: FakeDocumentFetcher, **overrides: Any) -> EntraExternalIdProvider:
    values: dict[str, Any] = {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "tenant_id": TENANT_ID,
        "discovery_url": DISCOVERY_URL,
        "required_scope": "access_as_user",
        "authorized_party": AUTHORIZED_PARTY,
        "clock_skew_seconds": 0,
        "jwks_cache_seconds": 3600,
        "connect_timeout_seconds": 2.0,
        "read_timeout_seconds": 7.0,
        "fetcher": fetcher,
    }
    values.update(overrides)
    return EntraExternalIdProvider(**values)


def _claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "pairwise-subject",
        "tid": TENANT_ID,
        "oid": OBJECT_ID,
        "iat": now - timedelta(seconds=1),
        "nbf": now - timedelta(seconds=1),
        "exp": now + timedelta(minutes=5),
        "ver": "2.0",
        "scp": "openid access_as_user reports.read",
        "azp": AUTHORIZED_PARTY,
        "email": "customer@example.test",
        "name": "Test Customer",
        "roles": ["provider-display-only"],
    }
    claims.update(overrides)
    return claims


def _token(private_key, key_id: str, claims: dict[str, Any] | None = None) -> str:
    return jwt.encode(
        claims or _claims(),
        private_key,
        algorithm="RS256",
        headers={"kid": key_id, "typ": "JWT"},
    )


def test_valid_access_token_returns_minimal_typed_principal_and_uses_cache():
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    fetcher = FakeDocumentFetcher([{"keys": [public_jwk]}])
    provider = _provider(fetcher)
    token = _token(private_key, "key-1")

    first = provider.validate_token(token, token_use=TokenUse.API_ACCESS_TOKEN)
    second = provider.validate_token(token, token_use=TokenUse.API_ACCESS_TOKEN)

    assert first.ok and second.ok
    assert first.value is not None
    assert first.value.provider == "entra_external_id"
    assert first.value.identity_subject == f"{TENANT_ID}:{OBJECT_ID}"
    assert first.value.internal_user_id is None
    assert first.value.email_hint == "customer@example.test"
    assert first.value.email_verified is False
    assert first.value.scopes == frozenset({"openid", "access_as_user", "reports.read"})
    assert first.value.roles == frozenset({"provider-display-only"})
    assert fetcher.calls == [DISCOVERY_URL, JWKS_URL]
    assert "customer@example.test" not in repr(first)
    assert token not in repr(first)


def test_email_is_verified_only_by_a_literal_boolean_claim():
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    provider = _provider(FakeDocumentFetcher([{"keys": [public_jwk]}]))

    verified = provider.validate_token(
        _token(private_key, "key-1", _claims(email_verified=True)),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )
    text_value = provider.validate_token(
        _token(private_key, "key-1", _claims(email_verified="true")),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert verified.ok and verified.value is not None
    assert verified.value.email_verified is True
    assert text_value.ok and text_value.value is not None
    assert text_value.value.email_verified is False


def test_preferred_username_never_becomes_a_verified_email():
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    provider = _provider(FakeDocumentFetcher([{"keys": [public_jwk]}]))
    claims = _claims(
        email_verified=True,
        preferred_username="unverified-alias@example.test",
    )
    claims.pop("email")

    result = provider.validate_token(
        _token(private_key, "key-1", claims),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert result.ok and result.value is not None
    assert result.value.email_hint == "unverified-alias@example.test"
    assert result.value.email_verified is False


@pytest.mark.parametrize(
    ("changed_claim", "changed_value"),
    [
        ("iss", "https://attacker.example.test/v2.0/"),
        ("aud", "wrong-audience"),
        ("tid", "55555555-5555-4555-8555-555555555555"),
        ("oid", "not-a-uuid"),
        ("ver", "1.0"),
        ("scp", "openid reports.read"),
        ("azp", "wrong-client"),
        ("idtyp", "app"),
    ],
)
def test_rejects_wrong_security_claims(changed_claim: str, changed_value: str):
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    provider = _provider(FakeDocumentFetcher([{"keys": [public_jwk]}]))

    result = provider.validate_token(
        _token(private_key, "key-1", _claims(**{changed_claim: changed_value})),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "identity_token_invalid"
    assert result.failure.retryable is False


@pytest.mark.parametrize("missing_claim", ["exp", "iat", "nbf", "aud", "iss", "sub", "tid", "oid"])
def test_rejects_missing_required_claim(missing_claim: str):
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    provider = _provider(FakeDocumentFetcher([{"keys": [public_jwk]}]))
    claims = _claims()
    claims.pop(missing_claim)

    result = provider.validate_token(
        _token(private_key, "key-1", claims),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code == "identity_token_invalid"


def test_expired_token_has_stable_non_retryable_failure():
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    provider = _provider(FakeDocumentFetcher([{"keys": [public_jwk]}]))
    result = provider.validate_token(
        _token(
            private_key,
            "key-1",
            _claims(exp=datetime.now(timezone.utc) - timedelta(seconds=1)),
        ),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code == "identity_token_expired"
    assert result.failure.retryable is False


def test_signature_algorithm_and_token_size_fail_before_network():
    _, public_jwk = _rsa_key_and_jwk("key-1")
    fetcher = FakeDocumentFetcher([{"keys": [public_jwk]}])
    provider = _provider(fetcher)
    hs_token = jwt.encode(
        _claims(),
        "a-test-secret-that-is-never-used-by-rs256",
        algorithm="HS256",
        headers={"kid": "key-1", "typ": "JWT"},
    )

    wrong_algorithm = provider.validate_token(
        hs_token,
        token_use=TokenUse.API_ACCESS_TOKEN,
    )
    oversized = provider.validate_token(
        "a" * (16 * 1024 + 1),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert not wrong_algorithm.ok and not oversized.ok
    assert fetcher.calls == []


def test_rejects_rsa_keys_smaller_than_2048_bits():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "small-key", "use": "sig", "alg": "RS256"})
    provider = _provider(FakeDocumentFetcher([{"keys": [public_jwk]}]))

    with pytest.warns(jwt.InsecureKeyLengthWarning):
        small_key_token = _token(private_key, "small-key")
    result = provider.validate_token(
        small_key_token,
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code == "identity_provider_unavailable"


def test_unknown_kid_forces_one_refresh_and_accepts_rotated_key():
    key_one, jwk_one = _rsa_key_and_jwk("key-1")
    key_two, jwk_two = _rsa_key_and_jwk("key-2")
    fetcher = FakeDocumentFetcher(
        [
            {"keys": [jwk_one]},
            {"keys": [jwk_one, jwk_two]},
        ]
    )
    provider = _provider(fetcher)

    assert provider.validate_token(
        _token(key_one, "key-1"),
        token_use=TokenUse.API_ACCESS_TOKEN,
    ).ok
    rotated = provider.validate_token(
        _token(key_two, "key-2"),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert rotated.ok
    assert fetcher.calls.count(JWKS_URL) == 2


def test_unknown_kid_refresh_is_throttled():
    known_key, known_jwk = _rsa_key_and_jwk("known")
    unknown_key, _ = _rsa_key_and_jwk("unknown")
    fetcher = FakeDocumentFetcher([{"keys": [known_jwk]}])
    provider = _provider(fetcher)

    # Warm the normal cache, then present the same unknown key twice.
    assert provider.validate_token(
        _token(known_key, "known"),
        token_use=TokenUse.API_ACCESS_TOKEN,
    ).ok
    token = _token(unknown_key, "unknown")
    assert not provider.validate_token(token, token_use=TokenUse.API_ACCESS_TOKEN).ok
    assert not provider.validate_token(token, token_use=TokenUse.API_ACCESS_TOKEN).ok

    assert fetcher.calls.count(JWKS_URL) == 2


def test_provider_document_outage_is_retryable_without_leaking_exception():
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    fetcher = FakeDocumentFetcher([{"keys": [public_jwk]}])
    fetcher.fail_urls.add(JWKS_URL)
    provider = _provider(fetcher)
    token = _token(private_key, "key-1")

    result = provider.validate_token(token, token_use=TokenUse.API_ACCESS_TOKEN)

    assert result.status is IntegrationStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == "identity_provider_unavailable"
    assert result.failure.retryable is True
    assert "sensitive upstream detail" not in result.failure.message
    assert token not in repr(result)


def test_discovery_issuer_must_exactly_match_configuration():
    private_key, public_jwk = _rsa_key_and_jwk("key-1")
    fetcher = FakeDocumentFetcher([{"keys": [public_jwk]}])
    fetcher.discovery["issuer"] = ISSUER.rstrip("/")
    provider = _provider(fetcher)

    result = provider.validate_token(
        _token(private_key, "key-1"),
        token_use=TokenUse.API_ACCESS_TOKEN,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code == "identity_provider_unavailable"


def test_unconfigured_and_wrong_token_use_fail_closed_without_network():
    _, public_jwk = _rsa_key_and_jwk("key-1")
    fetcher = FakeDocumentFetcher([{"keys": [public_jwk]}])
    unconfigured = _provider(fetcher, audience=None)
    configured = _provider(fetcher)

    missing = unconfigured.validate_token(
        "not-a-token",
        token_use=TokenUse.API_ACCESS_TOKEN,
    )
    wrong_use = configured.validate_token(
        "not-a-token",
        token_use=TokenUse.INTERNAL_SESSION,
    )

    assert missing.status is IntegrationStatus.NOT_CONFIGURED
    assert missing.failure is not None
    assert missing.failure.code == "identity_provider_not_configured"
    assert wrong_use.failure is not None
    assert wrong_use.failure.code == "identity_token_use_invalid"
    assert fetcher.calls == []


def test_internal_adapter_returns_canonical_internal_user_id():
    from app.core.tokens import create_user_access_token

    user_id = str(uuid.uuid4())
    token = create_user_access_token(
        user_id=user_id,
        email="internal@example.test",
        role="cliente",
    )

    result = InternalIdentityProvider().validate_token(
        token,
        token_use=TokenUse.INTERNAL_SESSION,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.internal_user_id == user_id
    assert result.value.internal_auth_generation == 0
    assert result.value.identity_subject == user_id
    assert result.value.email_hint == "internal@example.test"


def test_internal_adapter_preserves_signed_external_identity_context():
    from app.core.tokens import create_user_access_token

    user_id = str(uuid.uuid4())
    external_subject = f"{TENANT_ID}:{OBJECT_ID}"
    token = create_user_access_token(
        user_id=user_id,
        email="internal@example.test",
        role="cliente",
        identity_provider="entra_external_id",
        identity_issuer=ISSUER,
        identity_subject=external_subject,
    )

    result = InternalIdentityProvider().validate_token(
        token,
        token_use=TokenUse.INTERNAL_SESSION,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.provider == "internal"
    assert result.value.internal_user_id == user_id
    assert result.value.subject == user_id
    assert result.value.identity_subject == external_subject
    assert result.value.issuer == ISSUER


def test_internal_adapter_rejects_legacy_email_subject_without_uuid():
    from app.core.tokens import create_access_token

    token = create_access_token({"sub": "legacy@example.test", "role": "cliente"})
    result = InternalIdentityProvider().validate_token(
        token,
        token_use=TokenUse.INTERNAL_SESSION,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code == "identity_token_invalid"
