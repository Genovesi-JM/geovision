from __future__ import annotations

import base64
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import pytest

from app.core.config import Settings, settings
from app.core.passwords import hash_password
from app.core.tokens import create_access_token, create_user_access_token
from app.integrations.identity.internal import InternalIdentityProvider
from app.models import (
    Account,
    AccountMember,
    AuthIdentity,
    Company,
    CompanyUser,
    User,
    UserProfile,
)
from app.modules.identity.domain import ExternalPrincipal, TokenUse
from app.modules.organizations.services import get_user_company_id
from app.modules.identity.services import (
    IdentityResolutionError,
    IdentityService,
    build_authorization_context,
    issue_session_access_token,
)
from app.seed_data import seed_admin_users


GOOGLE_ISSUER = "https://accounts.google.com"
ENTRA_ISSUER = (
    "https://geovision-test.ciamlogin.com/"
    "11111111-1111-4111-8111-111111111111/v2.0/"
)
TENANT_ID = "11111111-1111-4111-8111-111111111111"


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


def _create_user(db_session, *, email: str | None = None, role: str = "cliente") -> User:
    user = User(
        email=email or _unique_email("identity-user"),
        password_hash=None,
        role=role,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _identity_settings(**overrides) -> Settings:
    values = {
        "env": "test",
        "accept_legacy_access_tokens": True,
        "identity_auto_link_verified_email": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _external_principal(
    *,
    subject: str | None = None,
    email: str | None = None,
    email_verified: bool = True,
    display_name: str = "Identity Test User",
) -> ExternalPrincipal:
    resolved_subject = subject or f"subject-{uuid.uuid4()}"
    return ExternalPrincipal(
        provider="entra_external_id",
        identity_subject=f"{TENANT_ID}:{resolved_subject}",
        subject=resolved_subject,
        issuer=ENTRA_ISSUER,
        tenant_id=TENANT_ID,
        email_hint=email or _unique_email("external-user"),
        email_verified=email_verified,
        display_name=display_name,
    )


def _validated_internal_principal(token: str):
    result = InternalIdentityProvider().validate_token(
        token,
        token_use=TokenUse.INTERNAL_SESSION,
    )
    assert result.ok, result.failure
    assert result.value is not None
    return result.value


def test_entra_configuration_is_complete_exact_and_redacted():
    config = Settings(
        _env_file=None,
        env="test",
        identity_provider="transition",
        entra_external_id_issuer=ENTRA_ISSUER,
        entra_external_id_audience="22222222-2222-4222-8222-222222222222",
        entra_external_id_tenant_id=TENANT_ID.upper(),
        entra_external_id_required_scope=" access_as_user ",
    )

    assert config.entra_external_id_configuration_complete is True
    assert config.entra_external_id_tenant_id == TENANT_ID
    assert config.entra_external_id_required_scope == "access_as_user"
    rendered = f"{config!r}\n{config.model_dump_json()}"
    assert TENANT_ID not in rendered
    assert "22222222-2222-4222-8222-222222222222" not in rendered

    with pytest.raises(ValueError, match="configured together"):
        Settings(
            _env_file=None,
            env="test",
            entra_external_id_issuer=ENTRA_ISSUER,
        )
    with pytest.raises(ValueError, match="must be a UUID"):
        Settings(
            _env_file=None,
            env="test",
            entra_external_id_issuer=ENTRA_ISSUER,
            entra_external_id_audience="geovision-api",
            entra_external_id_tenant_id="not-a-tenant-uuid",
        )
    with pytest.raises(ValueError, match="must use HTTPS"):
        Settings(
            _env_file=None,
            env="test",
            entra_external_id_issuer="http://tenant.example.test/v2.0/",
            entra_external_id_audience="geovision-api",
            entra_external_id_tenant_id=TENANT_ID,
        )

    for graph_audience in (
        "00000003-0000-0000-c000-000000000000",
        "api://00000003-0000-0000-c000-000000000000",
        "https://graph.microsoft.com/",
    ):
        with pytest.raises(ValueError, match="not Microsoft Graph"):
            Settings(
                _env_file=None,
                env="test",
                entra_external_id_issuer=ENTRA_ISSUER,
                entra_external_id_audience=graph_audience,
                entra_external_id_tenant_id=TENANT_ID,
            )

    for graph_scope in ("User.Read", "https://graph.microsoft.com/User.Read"):
        with pytest.raises(ValueError, match="not a Microsoft Graph scope"):
            Settings(
                _env_file=None,
                env="test",
                entra_external_id_issuer=ENTRA_ISSUER,
                entra_external_id_audience="geovision-api",
                entra_external_id_tenant_id=TENANT_ID,
                entra_external_id_required_scope=graph_scope,
            )


def test_deployed_runtime_rejects_generic_legacy_microsoft_tenant():
    values = {
        "_env_file": None,
        "env": "prod",
        "secret_key": "phase-three-production-signing-secret-value",
        "encryption_key": base64.urlsafe_b64encode(b"i" * 32).decode(),
        "frontend_base": "https://geovisionops.com",
        "backend_base": "https://api.geovisionops.com",
        "identity_provider": "transition",
        "entra_external_id_issuer": ENTRA_ISSUER,
        "entra_external_id_audience": "22222222-2222-4222-8222-222222222222",
        "entra_external_id_tenant_id": TENANT_ID,
        "microsoft_client_id": "legacy-browser-client",
        "microsoft_client_secret": "legacy-browser-secret",
    }

    with pytest.raises(ValueError, match="MICROSOFT_TENANT_ID"):
        Settings(**values, microsoft_tenant_id="common")

    pinned = Settings(**values, microsoft_tenant_id=TENANT_ID)
    assert pinned.microsoft_tenant_id == TENANT_ID

    internal_values = {**values, "identity_provider": "internal"}
    internal_values.pop("entra_external_id_issuer")
    internal_values.pop("entra_external_id_audience")
    internal_values.pop("entra_external_id_tenant_id")
    with pytest.raises(ValueError, match="MICROSOFT_TENANT_ID"):
        Settings(**internal_values, microsoft_tenant_id="organizations")


def test_deployed_admin_bootstrap_requires_a_strong_complete_pair():
    values = {
        "_env_file": None,
        "env": "prod",
        "frontend_base": "https://geovisionops.com",
        "backend_base": "https://api.geovisionops.com",
        "secret_key": "phase-three-production-signing-secret-value",
        "encryption_key": base64.urlsafe_b64encode(b"a" * 32).decode(),
    }

    with pytest.raises(ValueError, match="configured together"):
        Settings(**values, admin_emails="operator@example.com")
    with pytest.raises(ValueError, match="bootstrap policy"):
        Settings(
            **values,
            admin_emails="operator@example.com",
            admin_password="too-short",
        )

    configured = Settings(
        **values,
        admin_emails="operator@example.com",
        admin_password="strong-admin-bootstrap-password",
    )
    assert configured.admin_email_list == ("operator@example.com",)


def test_uuid_session_subject_survives_user_email_change(db_session):
    user = _create_user(db_session)
    original_id = user.id
    original_email = user.email
    token = issue_session_access_token(user)
    principal = _validated_internal_principal(token)

    assert str(uuid.UUID(principal.subject)) == original_id
    assert principal.internal_user_id == original_id
    assert principal.identity_subject == original_id

    user.email = _unique_email("renamed-user")
    db_session.commit()

    resolved = IdentityService(db_session).resolve_internal_principal(principal)
    assert resolved.user.id == original_id
    assert resolved.user.email == user.email
    assert resolved.user.email != original_email


def test_legacy_uuid_session_is_accepted_and_can_be_disabled(db_session, monkeypatch):
    user = _create_user(db_session)
    monkeypatch.setattr(settings, "accept_legacy_access_tokens", True)
    token = create_access_token(
        {"sub": user.email, "uid": user.id, "role": "cliente"}
    )

    principal = _validated_internal_principal(token)
    assert principal.internal_user_id == user.id
    resolved = IdentityService(
        db_session,
        _identity_settings(accept_legacy_access_tokens=True),
    ).resolve_internal_principal(principal)
    assert resolved.user.id == user.id

    monkeypatch.setattr(settings, "accept_legacy_access_tokens", False)
    rejected = InternalIdentityProvider().validate_token(
        token,
        token_use=TokenUse.INTERNAL_SESSION,
    )
    assert not rejected.ok
    assert rejected.failure is not None
    assert rejected.failure.code == "identity_token_invalid"


def test_legacy_email_only_session_cannot_attach_to_replacement_user(
    db_session,
    monkeypatch,
):
    original = _create_user(db_session)
    email = original.email
    monkeypatch.setattr(settings, "accept_legacy_access_tokens", True)
    email_only_token = create_access_token({"sub": email, "role": "cliente"})

    db_session.delete(original)
    db_session.commit()
    replacement = _create_user(db_session, email=email)

    result = InternalIdentityProvider().validate_token(
        email_only_token,
        token_use=TokenUse.INTERNAL_SESSION,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.code == "identity_token_invalid"
    assert db_session.get(User, replacement.id) is not None


def test_versioned_sessions_reject_mismatched_ids_and_unknown_versions():
    user_id = str(uuid.uuid4())
    common = {
        "uid": user_id,
        "iss": settings.internal_token_issuer,
        "aud": settings.internal_token_audience,
    }
    mismatched = create_access_token(
        {**common, "sub": str(uuid.uuid4()), "gv": 2},
    )
    future_version = create_access_token(
        {**common, "sub": user_id, "gv": 999},
    )

    for token in (mismatched, future_version):
        result = InternalIdentityProvider().validate_token(
            token,
            token_use=TokenUse.INTERNAL_SESSION,
        )
        assert not result.ok
        assert result.failure is not None
        assert result.failure.code == "identity_token_invalid"


def test_authorization_uses_database_roles_not_token_role(db_session):
    user = _create_user(db_session, role="cliente")
    account = Account(
        name=f"Identity workspace {uuid.uuid4().hex}",
        sector_focus="agro",
        entity_type="individual",
        customer_type="farm",
        dashboard_profile="farm",
        use_cases="[]",
        modules_enabled="[]",
    )
    db_session.add(account)
    db_session.flush()
    db_session.add(
        AccountMember(account_id=account.id, user_id=user.id, role="member")
    )
    db_session.commit()

    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role="admin",
    )
    principal = _validated_internal_principal(token)
    assert principal.roles == frozenset({"admin"})

    resolved = IdentityService(db_session).resolve_internal_principal(principal)
    context = build_authorization_context(
        db_session,
        resolved.user,
        principal,
        requested_workspace_id=account.id,
    )

    assert resolved.user.role == "cliente"
    assert context.user_id == user.id
    assert context.active_workspace_id == account.id
    assert "profile:read" in context.permissions
    assert "workspace:read" in context.permissions
    assert "platform:admin" not in context.permissions
    assert "workspace:manage" not in context.permissions


def test_company_access_requires_internal_user_membership_not_matching_email(
    db_session,
):
    user = _create_user(db_session)
    company = Company(name="Unbound legacy company", email=user.email)
    db_session.add(company)
    db_session.flush()
    email_only_membership = CompanyUser(
        company_id=company.id,
        user_id=None,
        email=user.email,
        name="Legacy email invitation",
        role="owner",
        is_active=True,
    )
    db_session.add(email_only_membership)
    db_session.commit()

    assert get_user_company_id(user, db_session) is None
    db_session.refresh(email_only_membership)
    assert email_only_membership.user_id is None

    email_only_membership.user_id = user.id
    db_session.commit()

    assert get_user_company_id(user, db_session) == company.id


def test_admin_seed_never_promotes_an_existing_email_account(
    db_session,
    monkeypatch,
):
    user = _create_user(db_session, email=_unique_email("configured-admin"))
    monkeypatch.setattr(settings, "admin_emails", user.email)
    monkeypatch.setattr(settings, "admin_password", "operator-supplied-password")

    with pytest.raises(RuntimeError, match="audited identity grant"):
        seed_admin_users()

    db_session.expire_all()
    assert db_session.get(User, user.id).role == "cliente"


def test_inactive_password_user_cannot_create_session_or_workspace(
    client,
    db_session,
):
    user = User(
        email=_unique_email("inactive-login"),
        password_hash=hash_password("valid-but-disabled-password"),
        role="cliente",
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()
    account_count = db_session.query(Account).count()

    response = client.post(
        "/auth/login",
        json={
            "email": user.email,
            "password": "valid-but-disabled-password",
        },
    )

    assert response.status_code == 401
    assert db_session.query(Account).count() == account_count
    assert (
        db_session.query(AccountMember)
        .filter(AccountMember.user_id == user.id)
        .count()
        == 0
    )


def test_verified_external_first_login_is_idempotent_and_creates_no_account(
    db_session,
):
    principal = _external_principal()
    account_count_before = db_session.query(Account).count()
    service = IdentityService(db_session, _identity_settings())

    first = service.resolve_external_principal(principal, provision=True)

    assert first.created is True
    assert str(uuid.UUID(first.user.id)) == first.user.id
    assert first.user.email == principal.email_hint
    assert first.identity is not None
    assert first.identity.user_id == first.user.id
    assert first.identity.issuer == principal.issuer
    assert first.identity.subject == principal.subject
    assert first.identity.raw_data is None
    assert db_session.get(UserProfile, first.user.id).full_name == principal.display_name
    assert (
        db_session.query(AccountMember)
        .filter(AccountMember.user_id == first.user.id)
        .count()
        == 0
    )
    assert db_session.query(Account).count() == account_count_before

    repeated = service.resolve_external_principal(principal, provision=True)

    assert repeated.created is False
    assert repeated.user.id == first.user.id
    assert repeated.identity is not None
    assert repeated.identity.id == first.identity.id
    assert db_session.query(User).filter(User.email == principal.email_hint).count() == 1
    assert (
        db_session.query(AuthIdentity)
        .filter(
            AuthIdentity.issuer == principal.issuer,
            AuthIdentity.subject == principal.subject,
        )
        .count()
        == 1
    )
    assert db_session.query(UserProfile).filter(UserProfile.user_id == first.user.id).count() == 1


def test_email_collision_requires_explicit_verified_link_compatibility(db_session):
    email = _unique_email("existing-user")
    existing = _create_user(db_session, email=email)
    principal = _external_principal(email=email)

    with pytest.raises(IdentityResolutionError) as rejected:
        IdentityService(db_session, _identity_settings()).resolve_external_principal(
            principal,
            provision=True,
        )

    assert rejected.value.code == "email_link_requires_confirmation"
    assert db_session.query(AuthIdentity).filter(AuthIdentity.user_id == existing.id).count() == 0
    assert db_session.get(UserProfile, existing.id) is None

    linked = IdentityService(
        db_session,
        _identity_settings(identity_auto_link_verified_email=True),
    ).resolve_external_principal(principal, provision=True)

    assert linked.created is False
    assert linked.user.id == existing.id
    assert linked.identity is not None
    assert linked.identity.user_id == existing.id
    assert linked.identity.email_verified is True
    assert db_session.get(UserProfile, existing.id) is not None


def test_external_email_collision_is_case_insensitive(db_session):
    canonical_email = _unique_email("mixed-case")
    local_part, domain = canonical_email.split("@", 1)
    existing = _create_user(
        db_session,
        email=f"{local_part.upper()}@{domain.upper()}",
    )
    principal = _external_principal(email=canonical_email)

    with pytest.raises(IdentityResolutionError) as rejected:
        IdentityService(db_session, _identity_settings()).resolve_external_principal(
            principal,
            provision=True,
        )

    assert rejected.value.code == "email_link_requires_confirmation"
    assert db_session.query(User).filter(
        User.id == existing.id
    ).one().email != canonical_email
    assert db_session.query(AuthIdentity).filter(
        AuthIdentity.user_id == existing.id
    ).count() == 0


def test_unverified_external_email_is_rejected_without_side_effects(db_session):
    principal = _external_principal(email_verified=False)
    counts_before = {
        "users": db_session.query(User).count(),
        "identities": db_session.query(AuthIdentity).count(),
        "profiles": db_session.query(UserProfile).count(),
        "accounts": db_session.query(Account).count(),
    }

    with pytest.raises(IdentityResolutionError) as rejected:
        IdentityService(db_session, _identity_settings()).resolve_external_principal(
            principal,
            provision=True,
        )

    assert rejected.value.code == "verified_email_required"
    assert db_session.query(User).count() == counts_before["users"]
    assert db_session.query(AuthIdentity).count() == counts_before["identities"]
    assert db_session.query(UserProfile).count() == counts_before["profiles"]
    assert db_session.query(Account).count() == counts_before["accounts"]


def test_external_subject_mapping_survives_user_email_change(db_session):
    subject = f"stable-subject-{uuid.uuid4()}"
    principal = _external_principal(subject=subject)
    service = IdentityService(db_session, _identity_settings())
    first = service.resolve_external_principal(principal, provision=True)
    original_email = first.user.email

    first.user.email = _unique_email("changed-external-user")
    changed_email = first.user.email
    db_session.commit()

    same_subject = _external_principal(
        subject=subject,
        email=original_email,
        display_name="Updated Display Name",
    )
    resolved = service.resolve_external_principal(same_subject, provision=True)

    assert resolved.user.id == first.user.id
    assert resolved.user.email == changed_email
    assert db_session.query(User).filter(User.email == original_email).count() == 0
    assert resolved.identity is not None
    assert resolved.identity.subject == subject


def test_issuer_qualified_identity_is_never_rebound_by_legacy_fallback(db_session):
    user = _create_user(db_session)
    shared_subject = f"provider-subject-{uuid.uuid4()}"
    existing = AuthIdentity(
        user_id=user.id,
        provider="google",
        provider_user_id=shared_subject,
        issuer="https://different-issuer.example.test",
        subject=shared_subject,
        email=user.email,
    )
    db_session.add(existing)
    db_session.commit()

    principal = ExternalPrincipal(
        provider="google",
        identity_subject=f"https://accounts.google.com|{shared_subject}",
        subject=shared_subject,
        issuer=GOOGLE_ISSUER,
        email_hint=user.email,
        email_verified=True,
    )
    with pytest.raises(IdentityResolutionError) as rejected:
        IdentityService(db_session, _identity_settings()).resolve_external_principal(
            principal,
            provision=False,
        )

    assert rejected.value.code == "identity_not_linked"
    db_session.refresh(existing)
    assert existing.issuer == "https://different-issuer.example.test"


def test_deleted_uuid_session_never_falls_back_to_replacement_email(db_session):
    original = _create_user(db_session)
    original_id = original.id
    email = original.email
    token = issue_session_access_token(original)
    principal = _validated_internal_principal(token)

    db_session.delete(original)
    db_session.commit()
    replacement = _create_user(db_session, email=email)
    assert replacement.id != original_id

    with pytest.raises(IdentityResolutionError) as rejected:
        IdentityService(
            db_session,
            _identity_settings(accept_legacy_access_tokens=True),
        ).resolve_internal_principal(principal)

    assert rejected.value.code == "inactive_or_missing_user"
    assert db_session.get(User, original_id) is None
    assert db_session.get(User, replacement.id) is not None
    assert db_session.query(User).filter(User.email == email).count() == 1


def _invoke_alembic(backend_dir: Path, database_path: Path, *arguments: str):
    environment = os.environ.copy()
    environment.pop("ENVIRONMENT", None)
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{database_path}",
            "ENV": "test",
            "SECRET_KEY": "identity-migration-test-secret-key-that-is-not-deployed",
        }
    )
    alembic = Path(sys.executable).with_name("alembic")
    return subprocess.run(
        [str(alembic), *arguments],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _run_alembic(backend_dir: Path, database_path: Path, *arguments: str) -> None:
    result = _invoke_alembic(backend_dir, database_path, *arguments)
    assert result.returncode == 0, result.stdout + result.stderr


def _invoke_alembic_offline(backend_dir: Path, *arguments: str):
    environment = os.environ.copy()
    environment.pop("ENVIRONMENT", None)
    environment.update(
        {
            "DATABASE_URL": "postgresql://geovision:unused@db.example/geovision",
            "ENV": "test",
            "SECRET_KEY": "identity-offline-sql-secret-key-that-is-not-deployed",
        }
    )
    alembic = Path(sys.executable).with_name("alembic")
    return subprocess.run(
        [str(alembic), *arguments],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _identity_schema(database_path: Path):
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info('auth_identities')")
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('auth_identities')")
        }
        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                """
                SELECT id, issuer, subject
                FROM auth_identities
                ORDER BY id
                """
            )
        }
    return columns, indexes, rows


def _company_user_schema(database_path: Path):
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info('company_users')")
        }
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('company_users')")
        }
        rows = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT id, user_id FROM company_users ORDER BY id"
            )
        }
    return columns, indexes, rows


def _table_schema(database_path: Path, table_name: str):
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info('{table_name}')")
        }
        indexes = {
            row[1]
            for row in connection.execute(f"PRAGMA index_list('{table_name}')")
        }
    return columns, indexes


def test_identity_migration_backfill_downgrade_and_reupgrade(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "identity-migration.sqlite3"
    _run_alembic(backend_dir, database_path, "upgrade", "account_profiles_v1")

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, ?, NULL, 'cliente', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                ("10000000-0000-4000-8000-000000000001", "migration-google@example.test"),
                ("10000000-0000-4000-8000-000000000002", "migration-microsoft@example.test"),
                ("10000000-0000-4000-8000-000000000003", "migration-blank@example.test"),
                ("10000000-0000-4000-8000-000000000004", "company-only@example.test"),
                ("10000000-0000-4000-8000-000000000005", "other-member@example.test"),
            ],
        )
        connection.execute(
            """
            INSERT INTO companies
                (id, name, email, country, sectors, status, subscription_plan,
                 max_users, max_sites, max_storage_gb, current_users,
                 current_sites, storage_used_gb, created_at, updated_at)
            VALUES
                ('migration-company-only', 'Company-only legacy record',
                 'COMPANY-ONLY@example.test', 'Angola', '[]', 'active',
                 'trial', 5, 10, 50, 0, 0, 0,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        connection.execute(
            """
            INSERT INTO refresh_tokens
                (id, token_hash, user_id, family_id, expires_at, revoked, created_at)
            VALUES ('migration-refresh', 'migration-refresh-hash',
                    '10000000-0000-4000-8000-000000000001', 'migration-family',
                    datetime('now', '+1 day'), 0, CURRENT_TIMESTAMP)
            """
        )
        connection.execute(
            """
            INSERT INTO reset_tokens
                (id, token, user_id, used, expires_at, created_at)
            VALUES
                ('migration-reset', 'legacy-plaintext-reset-secret',
                 '10000000-0000-4000-8000-000000000001', 0,
                 datetime('now', '+1 hour'), CURRENT_TIMESTAMP)
            """
        )
        connection.executemany(
            """
            INSERT INTO company_users
                (id, company_id, email, name, role, is_active, last_login, created_at)
            VALUES (?, ?, ?, ?, 'owner', 1, NULL, CURRENT_TIMESTAMP)
            """,
            [
                (
                    "migration-company-linked",
                    "migration-company-one",
                    "migration-google@example.test",
                    "Linked legacy member",
                ),
                (
                    "migration-company-orphan",
                    "migration-company-two",
                    "no-user@example.test",
                    "Orphan legacy member",
                ),
                (
                    "migration-company-unrelated",
                    "migration-company-only",
                    "other-member@example.test",
                    "Existing unrelated member",
                ),
            ],
        )
        connection.executemany(
            """
            INSERT INTO auth_identities
                (id, user_id, provider, provider_user_id, email, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                (
                    "migration-google",
                    "10000000-0000-4000-8000-000000000001",
                    "google",
                    "google-subject",
                    "migration-google@example.test",
                ),
                (
                    "migration-microsoft",
                    "10000000-0000-4000-8000-000000000002",
                    "microsoft",
                    "microsoft-object-id",
                    "migration-microsoft@example.test",
                ),
                (
                    "migration-blank",
                    "10000000-0000-4000-8000-000000000003",
                    "google",
                    "",
                    "migration-blank@example.test",
                ),
            ],
        )

    _run_alembic(backend_dir, database_path, "upgrade", "head")
    columns, indexes, rows = _identity_schema(database_path)
    company_columns, company_indexes, company_rows = _company_user_schema(
        database_path
    )
    family_columns, family_indexes = _table_schema(
        database_path,
        "refresh_token_families",
    )
    account_columns, account_indexes = _table_schema(database_path, "accounts")
    user_columns, user_indexes = _table_schema(database_path, "users")
    reset_columns, _ = _table_schema(database_path, "reset_tokens")
    oauth_state_columns, _ = _table_schema(database_path, "oauth_states")

    assert {
        "issuer",
        "subject",
        "tenant_id",
        "email_verified",
        "last_login_at",
    }.issubset(columns)
    assert "ix_auth_identities_provider_sub" in indexes
    assert "ix_auth_identities_issuer_subject" in indexes
    assert rows["migration-google"] == (GOOGLE_ISSUER, "google-subject")
    assert rows["migration-microsoft"] == (None, None)
    assert rows["migration-blank"] == (None, None)
    assert "user_id" in company_columns
    assert "ix_company_users_user_id" in company_indexes
    assert (
        company_rows["migration-company-linked"]
        == "10000000-0000-4000-8000-000000000001"
    )
    assert company_rows["migration-company-orphan"] is None
    assert (
        company_rows["migration-company-unrelated"]
        == "10000000-0000-4000-8000-000000000005"
    )
    with sqlite3.connect(database_path) as connection:
        company_only_link = connection.execute(
            """
            SELECT user_id FROM company_users
            WHERE company_id = 'migration-company-only'
              AND lower(trim(email)) = 'company-only@example.test'
            """
        ).fetchone()
    assert company_only_link == ("10000000-0000-4000-8000-000000000004",)
    with sqlite3.connect(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO company_users
                    (id, company_id, user_id, email, name, role,
                     is_active, last_login, created_at)
                VALUES
                    ('migration-duplicate-membership', 'migration-company-only',
                     '10000000-0000-4000-8000-000000000004',
                     'company-only@example.test', 'Duplicate owner', 'owner',
                     1, NULL, CURRENT_TIMESTAMP)
                """
            )
    assert {
        "auth_identity_id",
        "identity_provider",
        "identity_issuer",
        "identity_subject",
        "auth_generation",
        "revoked_at",
        "compromised_at",
        "expires_at",
    }.issubset(family_columns)
    assert "ix_refresh_token_families_user_id" in family_indexes
    assert "ix_refresh_token_families_auth_identity_id" in family_indexes
    assert "ix_users_email_normalized" in user_indexes
    assert "auth_generation" in user_columns
    assert "auth_generation" in reset_columns
    assert "onboarding_user_id" in account_columns
    assert "ix_accounts_onboarding_user_id" in account_indexes
    with sqlite3.connect(database_path) as connection:
        migrated_company_user_count = connection.execute(
            """
            SELECT current_users FROM companies
            WHERE id = 'migration-company-only'
            """
        ).fetchone()
        migrated_family = connection.execute(
            """
            SELECT user_id, identity_provider, identity_issuer, identity_subject,
                   auth_generation
            FROM refresh_token_families
            WHERE id = 'migration-family'
            """
        ).fetchone()
    assert migrated_company_user_count == (2,)
    assert migrated_family == (
        "10000000-0000-4000-8000-000000000001",
        "internal",
        None,
        "10000000-0000-4000-8000-000000000001",
        0,
    )
    assert {"provider", "code_verifier"}.issubset(oauth_state_columns)
    with sqlite3.connect(database_path) as connection:
        legacy_reset_used = connection.execute(
            "SELECT used FROM reset_tokens WHERE id = 'migration-reset'"
        ).fetchone()
    assert legacy_reset_used == (1,)

    _run_alembic(backend_dir, database_path, "downgrade", "account_profiles_v1")
    with sqlite3.connect(database_path) as connection:
        downgraded_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('auth_identities')")
        }
        downgraded_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('auth_identities')")
        }
        downgraded_company_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('company_users')")
        }
        downgraded_company_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('company_users')")
        }
        downgraded_family_table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'refresh_token_families'
            """
        ).fetchone()
        downgraded_oauth_state_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('oauth_states')")
        }
        downgraded_user_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('users')")
        }
        downgraded_user_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('users')")
        }
        downgraded_account_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('accounts')")
        }
        downgraded_reset_used = connection.execute(
            "SELECT used FROM reset_tokens WHERE id = 'migration-reset'"
        ).fetchone()
        downgraded_reset_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('reset_tokens')")
        }

    assert "issuer" not in downgraded_columns
    assert "subject" not in downgraded_columns
    assert "ix_auth_identities_issuer_subject" not in downgraded_indexes
    assert "ix_auth_identities_provider_sub" in downgraded_indexes
    assert "user_id" not in downgraded_company_columns
    assert "ix_company_users_user_id" not in downgraded_company_indexes
    assert downgraded_family_table is None
    assert "provider" not in downgraded_oauth_state_columns
    assert "code_verifier" not in downgraded_oauth_state_columns
    assert "ix_users_email_normalized" not in downgraded_user_indexes
    assert "auth_generation" not in downgraded_user_columns
    assert "auth_generation" not in downgraded_reset_columns
    assert "onboarding_user_id" not in downgraded_account_columns
    assert downgraded_reset_used == (1,)

    _run_alembic(backend_dir, database_path, "upgrade", "head")
    reupgraded_columns, reupgraded_indexes, reupgraded_rows = _identity_schema(
        database_path
    )
    (
        reupgraded_company_columns,
        reupgraded_company_indexes,
        reupgraded_company_rows,
    ) = _company_user_schema(database_path)
    reupgraded_family_columns, reupgraded_family_indexes = _table_schema(
        database_path,
        "refresh_token_families",
    )
    reupgraded_oauth_state_columns, _ = _table_schema(
        database_path,
        "oauth_states",
    )
    reupgraded_user_columns, reupgraded_user_indexes = _table_schema(
        database_path,
        "users",
    )
    reupgraded_reset_columns, _ = _table_schema(database_path, "reset_tokens")
    reupgraded_account_columns, reupgraded_account_indexes = _table_schema(
        database_path,
        "accounts",
    )
    assert "issuer" in reupgraded_columns
    assert "ix_auth_identities_issuer_subject" in reupgraded_indexes
    assert reupgraded_rows["migration-google"] == (
        GOOGLE_ISSUER,
        "google-subject",
    )
    assert reupgraded_rows["migration-microsoft"] == (None, None)
    assert reupgraded_rows["migration-blank"] == (None, None)
    assert "user_id" in reupgraded_company_columns
    assert "ix_company_users_user_id" in reupgraded_company_indexes
    assert "onboarding_user_id" in reupgraded_account_columns
    assert "ix_accounts_onboarding_user_id" in reupgraded_account_indexes
    assert "auth_generation" in reupgraded_user_columns
    assert "auth_generation" in reupgraded_reset_columns
    assert (
        reupgraded_company_rows["migration-company-linked"]
        == "10000000-0000-4000-8000-000000000001"
    )
    assert reupgraded_company_rows["migration-company-orphan"] is None
    assert (
        reupgraded_company_rows["migration-company-unrelated"]
        == "10000000-0000-4000-8000-000000000005"
    )
    assert "auth_identity_id" in reupgraded_family_columns
    assert "auth_generation" in reupgraded_family_columns
    assert "ix_refresh_token_families_auth_identity_id" in reupgraded_family_indexes
    assert "ix_users_email_normalized" in reupgraded_user_indexes
    assert {"provider", "code_verifier"}.issubset(
        reupgraded_oauth_state_columns
    )


def test_admin_email_compatibility_adapter_persists_internal_user_id(
    client,
    db_session,
):
    target = _create_user(db_session, email=_unique_email("company-member"))
    company = Company(name="Transition company", email="owner@example.test")
    db_session.add(company)
    db_session.commit()

    login = client.post(
        "/auth/login",
        json={"email": "teste@admin.com", "password": "123456"},
    )
    assert login.status_code == 200, login.text
    response = client.post(
        f"/admin/companies/{company.id}/users",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        params={"email": target.email.upper(), "role": "viewer"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == target.id
    db_session.expire_all()
    membership = (
        db_session.query(CompanyUser)
        .filter(CompanyUser.company_id == company.id)
        .one()
    )
    assert membership.user_id == target.id


def test_registration_immediately_binds_company_to_internal_user_id(
    client,
    db_session,
):
    response = client.post(
        "/auth/register",
        json={
            "email": _unique_email("new-company-owner"),
            "password": "strong-registration-password",
            "full_name": "New Company Owner",
            "customer_type": "farm",
            "sectors": ["agro"],
        },
    )

    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    db_session.expire_all()
    membership = (
        db_session.query(CompanyUser)
        .filter(CompanyUser.user_id == user_id)
        .one()
    )
    assert membership.is_active is True
    assert membership.role == "owner"

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["company_id"] == membership.company_id


def test_identity_migration_preflight_fails_before_ddl_for_google_collision(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "identity-preflight.sqlite3"
    _run_alembic(backend_dir, database_path, "upgrade", "account_profiles_v1")

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, ?, NULL, 'cliente', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                ("20000000-0000-4000-8000-000000000001", "collision-one@example.test"),
                ("20000000-0000-4000-8000-000000000002", "collision-two@example.test"),
            ],
        )
        connection.executemany(
            """
            INSERT INTO auth_identities
                (id, user_id, provider, provider_user_id, email, created_at)
            VALUES (?, ?, ?, 'shared-google-subject', ?, CURRENT_TIMESTAMP)
            """,
            [
                (
                    "collision-identity-one",
                    "20000000-0000-4000-8000-000000000001",
                    "google",
                    "collision-one@example.test",
                ),
                (
                    "collision-identity-two",
                    "20000000-0000-4000-8000-000000000002",
                    "Google",
                    "collision-two@example.test",
                ),
            ],
        )

    failed = _invoke_alembic(backend_dir, database_path, "upgrade", "head")

    assert failed.returncode != 0
    assert "duplicate Google subjects" in failed.stdout + failed.stderr
    with sqlite3.connect(database_path) as connection:
        identity_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info('auth_identities')")
        }
        user_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('users')")
        }
    assert "issuer" not in identity_columns
    assert "ix_users_email_normalized" not in user_indexes


def test_identity_migration_preflight_rejects_non_uuid_user_ids(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "identity-id-preflight.sqlite3"
    _run_alembic(backend_dir, database_path, "upgrade", "account_profiles_v1")

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, ?, NULL, 'cliente', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                ("historical-non-uuid-id", "historical@example.test"),
                (
                    "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
                    "uppercase-id@example.test",
                ),
            ],
        )

    failed = _invoke_alembic(backend_dir, database_path, "upgrade", "head")

    assert failed.returncode != 0
    assert "user IDs are not canonical UUIDs" in failed.stdout + failed.stderr
    with sqlite3.connect(database_path) as connection:
        identity_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info('auth_identities')")
        }
        user_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list('users')")
        }
    assert "issuer" not in identity_columns
    assert "ix_users_email_normalized" not in user_indexes


def test_identity_migration_preflight_rejects_blank_refresh_family(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "identity-family-preflight.sqlite3"
    _run_alembic(backend_dir, database_path, "upgrade", "account_profiles_v1")
    user_id = "40000000-0000-4000-8000-000000000001"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, 'blank-family@example.test', NULL, 'cliente', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )
        connection.execute(
            """
            INSERT INTO refresh_tokens
                (id, token_hash, user_id, family_id, expires_at, revoked, created_at)
            VALUES ('blank-family-token', 'blank-family-hash', ?, '   ',
                    datetime('now', '+1 day'), 0, CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )

    failed = _invoke_alembic(backend_dir, database_path, "upgrade", "head")

    assert failed.returncode != 0
    assert "blank refresh family IDs" in failed.stdout + failed.stderr
    with sqlite3.connect(database_path) as connection:
        identity_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info('auth_identities')")
        }
    assert "issuer" not in identity_columns


def test_identity_migration_preflight_rejects_duplicate_company_membership(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "identity-company-preflight.sqlite3"
    _run_alembic(backend_dir, database_path, "upgrade", "account_profiles_v1")
    user_id = "50000000-0000-4000-8000-000000000001"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO users
                (id, email, password_hash, role, is_active, created_at, updated_at)
            VALUES (?, 'duplicate-member@example.test', NULL, 'cliente', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (user_id,),
        )
        connection.executemany(
            """
            INSERT INTO company_users
                (id, company_id, email, name, role, is_active, last_login, created_at)
            VALUES (?, 'duplicate-company', ?, NULL, 'viewer', 1, NULL,
                    CURRENT_TIMESTAMP)
            """,
            [
                ("duplicate-company-user-one", "duplicate-member@example.test"),
                ("duplicate-company-user-two", "DUPLICATE-MEMBER@example.test"),
            ],
        )

    failed = _invoke_alembic(backend_dir, database_path, "upgrade", "head")

    assert failed.returncode != 0
    assert "duplicate company membership" in failed.stdout + failed.stderr
    with sqlite3.connect(database_path) as connection:
        company_columns = {
            row[1] for row in connection.execute("PRAGMA table_info('company_users')")
        }
    assert "user_id" not in company_columns


def test_identity_migration_rejects_incomplete_offline_sql_generation():
    backend_dir = Path(__file__).resolve().parents[1]

    generated = _invoke_alembic_offline(
        backend_dir,
        "upgrade",
        "account_profiles_v1:identity_boundary_v1",
        "--sql",
    )

    assert generated.returncode != 0
    assert "requires an online migration" in generated.stdout + generated.stderr
