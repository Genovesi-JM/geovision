from __future__ import annotations

import hashlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.core.passwords import hash_password
from app.core.tokens import decode_access_token
from app.core.time import utc_now
from app.models import (
    Account,
    AccountMember,
    AuthIdentity,
    Company,
    CompanyUser,
    RefreshTokenFamily,
    ResetToken,
    User,
    UserProfile,
)
from app.modules.identity.domain import ExternalPrincipal, TokenUse
from app.routers.auth import get_external_identity_provider


ISSUER = (
    "https://geovision-test.ciamlogin.com/"
    "11111111-1111-4111-8111-111111111111/v2.0/"
)
TENANT_ID = "11111111-1111-4111-8111-111111111111"


def _reset_token(raw_token: str, user_id: str) -> ResetToken:
    return ResetToken(
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        user_id=user_id,
        expires_at=utc_now() + timedelta(minutes=5),
    )


class StaticIdentityProvider:
    provider_name = "entra_external_id"

    def __init__(self, result):
        self.result = result
        self.calls = []

    def validate_token(self, token, *, token_use, expected_nonce=None):
        self.calls.append((token, token_use, expected_nonce))
        return self.result


def _principal(*, verified: bool = True) -> ExternalPrincipal:
    object_id = str(uuid.uuid4())
    return ExternalPrincipal(
        provider="entra_external_id",
        issuer=ISSUER,
        subject=f"pairwise-{uuid.uuid4()}",
        identity_subject=f"{TENANT_ID}:{object_id}",
        tenant_id=TENANT_ID,
        object_id=object_id,
        email_hint=f"external-{uuid.uuid4().hex}@example.com",
        email_verified=verified,
        display_name="External Test User",
        scopes=frozenset({"access_as_user"}),
    )


def _success(principal: ExternalPrincipal):
    return IntegrationResult.succeeded(
        provider="entra_external_id",
        operation="validate_api_access_token",
        value=principal,
    )


def _failure(code: str, *, retryable: bool = False, unavailable: bool = False):
    return IntegrationResult.failed(
        provider="entra_external_id",
        operation="validate_api_access_token",
        status=(IntegrationStatus.RETRYING if unavailable else IntegrationStatus.FAILED),
        failure=IntegrationFailure(
            code=code,
            message="identity token validation failed",
            retryable=retryable,
        ),
    )


def test_auth_responses_are_never_browser_cached(client):
    response = client.get("/auth/status")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_static_web_login_does_not_mint_an_untracked_refresh_family(
    client,
    db_session,
):
    email = f"web-access-only-{uuid.uuid4().hex}@example.com"
    user = User(
        email=email,
        password_hash=hash_password("web-password-123"),
        role="cliente",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    response = client.post(
        "/auth/login",
        headers={"X-GeoVision-Client": "web"},
        json={"email": email, "password": "web-password-123"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["refresh_token"] is None
    assert (
        db_session.query(RefreshTokenFamily)
        .filter(RefreshTokenFamily.user_id == user.id)
        .count()
        == 0
    )


def test_external_session_provisions_profile_only_and_preserves_identity_context(
    client,
    db_session,
):
    principal = _principal()
    provider = StaticIdentityProvider(_success(principal))
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        response = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer validated-upstream-token"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)

    assert response.status_code == 200, response.text
    body = response.json()
    user_id = body["user"]["id"]
    assert str(uuid.UUID(user_id)) == user_id
    assert body["account"] is None
    assert provider.calls == [
        ("validated-upstream-token", TokenUse.API_ACCESS_TOKEN, None)
    ]

    db_session.expire_all()
    assert db_session.get(User, user_id) is not None
    assert db_session.get(UserProfile, user_id).full_name == "External Test User"
    assert (
        db_session.query(AccountMember).filter(AccountMember.user_id == user_id).count()
        == 0
    )
    identity = (
        db_session.query(AuthIdentity)
        .filter(
            AuthIdentity.issuer == principal.issuer,
            AuthIdentity.subject == principal.subject,
        )
        .one()
    )
    assert identity.user_id == user_id

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200, me.text
    context = me.json()["authorization_context"]
    assert context == {
        "user_id": user_id,
        "identity_subject": principal.identity_subject,
        "active_workspace_id": None,
        "active_organization_id": None,
        "permissions": ["profile:read"],
    }
    denied_workspace = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {body['access_token']}",
            "X-Account-ID": str(uuid.uuid4()),
        },
    )
    assert denied_workspace.status_code == 403

    onboarding = client.post(
        "/auth/onboarding",
        headers={"Authorization": f"Bearer {body['access_token']}"},
        json={"customer_type": "farm", "sectors": ["agro"]},
    )
    assert onboarding.status_code == 200, onboarding.text
    assert onboarding.json()["access_token"] == body["access_token"]
    onboarding_claims = decode_access_token(onboarding.json()["access_token"])
    assert onboarding_claims["idp"] == principal.provider
    assert onboarding_claims["identity_issuer"] == principal.issuer
    assert onboarding_claims["identity_subject"] == principal.identity_subject

    db_session.expire_all()
    company_membership = (
        db_session.query(CompanyUser)
        .filter(CompanyUser.user_id == user_id)
        .one()
    )
    after_onboarding = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert after_onboarding.status_code == 200, after_onboarding.text
    assert after_onboarding.json()["company_id"] == company_membership.company_id

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    refresh_body = refreshed.json()
    refresh_claims = decode_access_token(refresh_body["access_token"])
    assert refresh_claims["idp"] == principal.provider
    assert refresh_claims["identity_issuer"] == principal.issuer
    assert refresh_claims["identity_subject"] == principal.identity_subject

    replay = client.post(
        "/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert replay.status_code == 401
    family_revoked = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_body["refresh_token"]},
    )
    assert family_revoked.status_code == 401

    forgot = client.post("/auth/forgot-password", json={"email": body["user"]["email"]})
    assert forgot.status_code == 202
    assert (
        db_session.query(ResetToken).filter(ResetToken.user_id == user_id).count()
        == 0
    )


def test_concurrent_onboarding_is_idempotent_on_sqlite(client, db_session):
    principal = _principal()
    provider = StaticIdentityProvider(_success(principal))
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        exchange = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer validated-upstream-token"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)
    assert exchange.status_code == 200, exchange.text

    user_id = exchange.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {exchange.json()['access_token']}"}
    barrier = threading.Barrier(2)

    def onboard():
        barrier.wait(timeout=5)
        return client.post(
            "/auth/onboarding",
            headers=headers,
            json={"customer_type": "farm", "sectors": ["agro"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: onboard(), range(2)))

    assert [response.status_code for response in responses] == [200, 200]
    account_ids = {response.json()["account"]["id"] for response in responses}
    assert len(account_ids) == 1

    db_session.expire_all()
    assert (
        db_session.query(AccountMember)
        .filter(AccountMember.user_id == user_id)
        .count()
        == 1
    )
    assert (
        db_session.query(Account)
        .filter(Account.onboarding_user_id == user_id)
        .count()
        == 1
    )
    assert (
        db_session.query(CompanyUser)
        .filter(CompanyUser.user_id == user_id)
        .count()
        == 1
    )
    company_id = (
        db_session.query(CompanyUser.company_id)
        .filter(CompanyUser.user_id == user_id)
        .scalar()
    )
    assert db_session.query(Company).filter(Company.id == company_id).count() == 1


def test_external_session_rejects_unverified_first_login_without_side_effects(
    client,
    db_session,
):
    principal = _principal(verified=False)
    provider = StaticIdentityProvider(_success(principal))
    before = db_session.query(User).count()
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        response = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer valid-but-unverified"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)

    assert response.status_code == 403
    db_session.expire_all()
    assert db_session.query(User).count() == before
    assert (
        db_session.query(AuthIdentity)
        .filter(
            AuthIdentity.issuer == principal.issuer,
            AuthIdentity.subject == principal.subject,
        )
        .count()
        == 0
    )


def test_external_session_maps_expired_and_invalid_tokens_to_unauthorized(client):
    for code in ("identity_token_expired", "identity_token_invalid"):
        provider = StaticIdentityProvider(_failure(code))
        client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
        try:
            response = client.post(
                "/auth/identity/session",
                headers={"Authorization": "Bearer rejected-token"},
            )
        finally:
            client.app.dependency_overrides.pop(get_external_identity_provider, None)
        assert response.status_code == 401


def test_external_session_maps_retryable_provider_failure_to_unavailable(client):
    provider = StaticIdentityProvider(
        _failure("identity_provider_unavailable", retryable=True, unavailable=True)
    )
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        response = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer temporarily-unverifiable"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)

    assert response.status_code == 503


def test_external_session_requires_bearer_credentials_before_validation(client):
    provider = StaticIdentityProvider(_success(_principal()))
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        missing = client.post("/auth/identity/session")
        wrong_scheme = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Basic ignored"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)

    assert missing.status_code == 401
    assert wrong_scheme.status_code == 401
    assert provider.calls == []


def test_external_refresh_requires_the_identity_mapping(client, db_session):
    principal = _principal()
    provider = StaticIdentityProvider(_success(principal))
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        session = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer validated-upstream-token"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)
    assert session.status_code == 200, session.text

    identity = (
        db_session.query(AuthIdentity)
        .filter(
            AuthIdentity.issuer == principal.issuer,
            AuthIdentity.subject == principal.subject,
        )
        .one()
    )
    db_session.delete(identity)
    db_session.commit()

    rejected = client.post(
        "/auth/refresh",
        json={"refresh_token": session.json()["refresh_token"]},
    )
    assert rejected.status_code == 401


def test_external_refresh_never_outlives_absolute_family_deadline(client, db_session):
    principal = _principal()
    provider = StaticIdentityProvider(_success(principal))
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        session = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer validated-upstream-token"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)
    assert session.status_code == 200, session.text

    user_id = session.json()["user"]["id"]
    family = db_session.query(RefreshTokenFamily).filter(
        RefreshTokenFamily.user_id == user_id
    ).one()
    family.expires_at = utc_now() + timedelta(minutes=5)
    family_deadline = family.expires_at
    db_session.commit()

    refreshed = client.post(
        "/auth/refresh",
        json={"refresh_token": session.json()["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert decode_access_token(refreshed.json()["access_token"])["exp"] <= int(
        family_deadline.replace(tzinfo=timezone.utc).timestamp()
    )

    family.expires_at = utc_now()
    db_session.commit()
    expired = client.post(
        "/auth/refresh",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert expired.status_code == 401


def test_external_only_user_cannot_bootstrap_a_local_password(client, db_session):
    principal = _principal()
    provider = StaticIdentityProvider(_success(principal))
    client.app.dependency_overrides[get_external_identity_provider] = lambda: provider
    try:
        session = client.post(
            "/auth/identity/session",
            headers={"Authorization": "Bearer validated-upstream-token"},
        )
    finally:
        client.app.dependency_overrides.pop(get_external_identity_provider, None)
    assert session.status_code == 200, session.text
    user_id = session.json()["user"]["id"]

    raw_reset_token = f"legacy-reset-{uuid.uuid4().hex}"
    reset = _reset_token(raw_reset_token, user_id)
    db_session.add(reset)
    db_session.commit()

    response = client.post(
        "/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "must-not-be-installed"},
    )

    assert response.status_code == 400
    db_session.expire_all()
    assert db_session.get(User, user_id).password_hash is None
    assert db_session.get(ResetToken, reset.id).used is True


def test_password_reset_secret_uses_fragment_and_is_hashed_at_rest(
    client,
    db_session,
    monkeypatch,
):
    email = f"reset-link-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "old-password-123",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert registered.status_code == 201, registered.text
    links = []
    monkeypatch.setattr(
        "app.routers.auth.send_reset_email",
        lambda recipient, link: links.append((recipient, link)),
    )

    requested = client.post("/auth/forgot-password", json={"email": email})

    assert requested.status_code == 202
    assert len(links) == 1
    recipient, link = links[0]
    assert recipient == email
    parsed = urlsplit(link)
    assert parse_qs(parsed.query) == {"v": ["8"]}
    assert "token" not in parse_qs(parsed.query)
    raw_token = parse_qs(parsed.fragment)["token"][0]
    stored = (
        db_session.query(ResetToken)
        .filter(ResetToken.user_id == registered.json()["user"]["id"])
        .one()
    )
    assert stored.token_hash == hashlib.sha256(raw_token.encode()).hexdigest()
    assert stored.token_hash != raw_token
    assert stored.auth_generation == 0


def test_password_reset_is_single_use_and_revokes_refresh_families(client, db_session):
    email = f"reset-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "old-password-123",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    user_id = body["user"]["id"]
    raw_reset_token = f"reset-{uuid.uuid4().hex}"
    older_raw_reset_token = f"reset-older-{uuid.uuid4().hex}"
    reset = _reset_token(raw_reset_token, user_id)
    older_reset = _reset_token(older_raw_reset_token, user_id)
    db_session.add_all([reset, older_reset])
    db_session.commit()

    changed = client.post(
        "/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "new-password-456"},
    )
    replay = client.post(
        "/auth/reset-password",
        json={"token": raw_reset_token, "new_password": "attacker-password-789"},
    )
    older_link_replay = client.post(
        "/auth/reset-password",
        json={"token": older_raw_reset_token, "new_password": "attacker-password-789"},
    )

    assert changed.status_code == 200, changed.text
    assert replay.status_code == 400
    assert older_link_replay.status_code == 400
    assert client.post(
        "/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    ).status_code == 401
    assert client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    ).status_code == 401
    db_session.expire_all()
    assert db_session.get(User, user_id).auth_generation == 1
    assert all(
        family.revoked_at is not None
        for family in db_session.query(RefreshTokenFamily).filter(
            RefreshTokenFamily.user_id == user_id
        )
    )


def test_reset_link_from_an_older_auth_generation_cannot_change_password(
    client,
    db_session,
):
    email = f"reset-generation-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "old-password-123",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["user"]["id"]
    first_raw = f"reset-first-{uuid.uuid4().hex}"
    stale_raw = f"reset-stale-{uuid.uuid4().hex}"
    db_session.add_all(
        [
            _reset_token(first_raw, user_id),
            _reset_token(stale_raw, user_id),
        ]
    )
    db_session.commit()

    winner = client.post(
        "/auth/reset-password",
        json={"token": first_raw, "new_password": "winner-password-456"},
    )
    stale = client.post(
        "/auth/reset-password",
        json={"token": stale_raw, "new_password": "stale-password-789"},
    )

    assert winner.status_code == 200, winner.text
    assert stale.status_code == 400
    assert client.post(
        "/auth/login",
        json={"email": email, "password": "winner-password-456"},
    ).status_code == 200
    assert client.post(
        "/auth/login",
        json={"email": email, "password": "stale-password-789"},
    ).status_code == 401


def test_concurrent_distinct_reset_links_have_one_sqlite_winner(
    client,
    db_session,
    monkeypatch,
):
    if db_session.bind.dialect.name != "sqlite":
        pytest.skip("SQLite-specific compare-and-swap regression test")

    email = f"reset-concurrent-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "old-password-123",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["user"]["id"]
    attempts = {
        f"reset-a-{uuid.uuid4().hex}": "winner-a-password",
        f"reset-b-{uuid.uuid4().hex}": "winner-b-password",
    }
    db_session.add_all(
        [_reset_token(raw_token, user_id) for raw_token in attempts]
    )
    db_session.commit()

    from app.routers import auth as auth_router

    original_hash = auth_router.hash_password
    both_requests_validated = threading.Barrier(2)

    def synchronized_hash(password):
        if password in attempts.values():
            both_requests_validated.wait(timeout=5)
        return original_hash(password)

    monkeypatch.setattr(auth_router, "hash_password", synchronized_hash)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            raw_token: pool.submit(
                client.post,
                "/auth/reset-password",
                json={"token": raw_token, "new_password": password},
            )
            for raw_token, password in attempts.items()
        }
        responses = {
            raw_token: future.result(timeout=15)
            for raw_token, future in futures.items()
        }

    assert sorted(response.status_code for response in responses.values()) == [
        200,
        400,
    ]
    winning_token = next(
        raw_token
        for raw_token, response in responses.items()
        if response.status_code == 200
    )
    for raw_token, password in attempts.items():
        login = client.post(
            "/auth/login",
            headers={"X-GeoVision-Client": "web"},
            json={"email": email, "password": password},
        )
        assert login.status_code == (200 if raw_token == winning_token else 401)

    db_session.expire_all()
    assert db_session.get(User, user_id).auth_generation == 1
    assert all(
        token.used
        for token in db_session.query(ResetToken).filter(
            ResetToken.user_id == user_id
        )
    )


def test_login_racing_password_reset_cannot_leave_a_usable_stale_session(
    client,
    db_session,
    monkeypatch,
):
    email = f"reset-race-{uuid.uuid4().hex}@example.com"
    registered = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "old-password-123",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["user"]["id"]
    raw_reset_token = f"reset-race-{uuid.uuid4().hex}"
    db_session.add(_reset_token(raw_reset_token, user_id))
    db_session.commit()

    from app.routers import auth as auth_router

    original_verify = auth_router.verify_password
    verification_complete = threading.Event()
    allow_login_to_continue = threading.Event()

    def gated_verify(password, password_hash):
        valid = original_verify(password, password_hash)
        if password == "old-password-123" and valid:
            verification_complete.set()
            assert allow_login_to_continue.wait(timeout=5)
        return valid

    monkeypatch.setattr(auth_router, "verify_password", gated_verify)
    with ThreadPoolExecutor(max_workers=2) as pool:
        login_future = pool.submit(
            client.post,
            "/auth/login",
            json={"email": email, "password": "old-password-123"},
        )
        assert verification_complete.wait(timeout=5)
        reset = client.post(
            "/auth/reset-password",
            json={
                "token": raw_reset_token,
                "new_password": "new-password-456",
            },
        )
        allow_login_to_continue.set()
        raced_login = login_future.result(timeout=10)

    assert reset.status_code == 200, reset.text
    assert raced_login.status_code in {200, 401}
    if raced_login.status_code == 200:
        assert client.get(
            "/auth/me",
            headers={
                "Authorization": f"Bearer {raced_login.json()['access_token']}"
            },
        ).status_code == 401
        assert client.post(
            "/auth/refresh",
            json={"refresh_token": raced_login.json()["refresh_token"]},
        ).status_code == 401

    db_session.expire_all()
    current_generation = db_session.get(User, user_id).auth_generation
    assert current_generation == 1
    assert all(
        family.revoked_at is not None
        or family.auth_generation != current_generation
        for family in db_session.query(RefreshTokenFamily).filter(
            RefreshTokenFamily.user_id == user_id
        )
    )


@pytest.mark.parametrize(
    "new_password",
    ["", "short", chr(0x1F642) * 19],
)
def test_password_reset_rejects_weak_or_bcrypt_truncated_values(
    client,
    db_session,
    new_password,
):
    registered = client.post(
        "/auth/register",
        json={
            "email": f"reset-policy-{uuid.uuid4().hex}@example.com",
            "password": "old-password-123",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )
    assert registered.status_code == 201, registered.text
    user_id = registered.json()["user"]["id"]
    raw_reset_token = f"reset-policy-{uuid.uuid4().hex}"
    reset = _reset_token(raw_reset_token, user_id)
    db_session.add(reset)
    db_session.commit()

    rejected = client.post(
        "/auth/reset-password",
        json={"token": raw_reset_token, "new_password": new_password},
    )

    assert rejected.status_code == 422
    db_session.expire_all()
    assert db_session.get(ResetToken, reset.id).used is False


def test_registration_rejects_password_that_exceeds_bcrypt_byte_limit(client):
    response = client.post(
        "/auth/register",
        json={
            "email": f"registration-policy-{uuid.uuid4().hex}@example.com",
            "password": chr(0x1F642) * 19,
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )

    assert response.status_code == 422
