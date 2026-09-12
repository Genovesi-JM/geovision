"""Isolated auth contract regression tests, with no dotenv or persistent data.

Run directly with Python (not the legacy pytest conftest). The real auth,
profile and account routers use a fresh in-memory database for every test.
"""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from pydantic_settings import BaseSettings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_original_settings_init = BaseSettings.__init__


def _synthetic_settings_init(self, *args, **kwargs):
    kwargs["_env_file"] = None
    return _original_settings_init(self, *args, **kwargs)


# Disable dotenv before importing any application module, including the global
# Settings instance. These fixed test values never authenticate to a service.
with patch.dict(
    os.environ,
    {
        "ENV": "test",
        "DATABASE_URL": "sqlite://",
        "ACCOUNTS_DATABASE_URL": "sqlite://",
        "SECRET_KEY": "synthetic-staff-auth-tests-only-0123456789abcdef",
        "RUN_MIGRATIONS_ON_STARTUP": "false",
        "STARTUP_COMPATIBILITY_BOOTSTRAP": "false",
    },
    clear=True,
), patch.object(BaseSettings, "__init__", _synthetic_settings_init):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base, get_db
    from app.core.security import hash_password
    from app.core.time import utc_now
    from app.models import (
        Account,
        AccountMember,
        Company,
        CompanyUser,
        InternalRoleAssignment,
        Invitation,
        RefreshTokenFamily,
        User,
        UserProfile,
    )
    from app.modules.organizations.domain import InternalRole
    from app.routers import accounts, auth, me


PASSWORD = "Synthetic-password-123!"
PASSWORD_HASH = hash_password(PASSWORD)


class StaffAuthOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(self.engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        application = FastAPI()
        application.include_router(auth.router)
        application.include_router(me.router)
        application.include_router(accounts.router)

        def isolated_db():
            yield self.db

        application.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(application)

    def tearDown(self):
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def user(self, *, role="cliente", internal_role=None, active_assignment=True):
        user = User(
            email=f"synthetic-{uuid.uuid4().hex}@example.com",
            password_hash=PASSWORD_HASH,
            role=role,
            is_active=True,
        )
        self.db.add(user)
        self.db.flush()
        if internal_role:
            self.db.add(
                InternalRoleAssignment(
                    user_id=user.id,
                    role=internal_role,
                    is_active=active_assignment,
                )
            )
        self.db.commit()
        return user

    def login(self, user, *, password=PASSWORD, client="web", expected_status=200):
        response = self.client.post(
            "/auth/login",
            headers={"X-GeoVision-Client": client},
            json={"email": user.email, "password": password},
        )
        self.assertEqual(response.status_code, expected_status, response.text)
        return response.json()

    def customer_counts(self):
        return tuple(
            self.db.query(model).count()
            for model in (UserProfile, Company, CompanyUser, Account, AccountMember)
        )

    def workspace(self, user, *, member_status="active", account_status="active"):
        organization = Company(
            name="Explicit Spanish customer",
            email=f"company-{uuid.uuid4().hex}@example.com",
            country="Spain",
            timezone="Europe/Madrid",
            organization_type="customer",
            status="active",
        )
        self.db.add(organization)
        self.db.flush()
        account = Account(
            organization_id=organization.id,
            name="Explicit environmental workspace",
            sector_focus="environment",
            customer_type="business",
            dashboard_profile="business",
            entity_type="org",
            status=account_status,
        )
        self.db.add(account)
        self.db.flush()
        self.db.add(
            AccountMember(
                account_id=account.id,
                user_id=user.id,
                role="viewer",
                status=member_status,
            )
        )
        self.db.commit()
        return account

    def invite(self, user):
        owner = self.user()
        account = self.workspace(owner)
        membership = CompanyUser(
            company_id=account.organization_id,
            user_id=None,
            email=user.email,
            role="viewer",
            status="invited",
            is_active=False,
        )
        self.db.add(membership)
        self.db.flush()
        invitation = Invitation(
            token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
            token_prefix="synthetic",
            organization_id=account.organization_id,
            workspace_id=account.id,
            membership_id=membership.id,
            target_email=user.email,
            pending_email_key=user.email,
            intended_role="viewer",
            invited_by_user_id=owner.id,
            expires_at=utc_now() + timedelta(hours=1),
        )
        self.db.add(invitation)
        self.db.commit()
        return invitation

    def assert_empty_staff_reads(self, body):
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        profile = self.client.get("/auth/me", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        data = profile.json()
        self.assertIsNone(data["account"])
        self.assertEqual(data["account_id"], "")
        self.assertEqual(data["account_name"], "")
        self.assertEqual(data["company_id"], "")
        self.assertIsNone(data["customer_type"])
        self.assertIsNone(data["dashboard_profile"])
        self.assertEqual(data["sector_focus"], "")
        self.assertEqual(data["use_cases"], [])
        self.assertTrue(data["authorization_context"]["internal_roles"])
        summary = self.client.get("/me", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["accounts"], [])
        self.assertIsNone(summary.json()["profile"])
        self.assertIsNone(summary.json()["default_account_id"])
        memberships = self.client.get("/accounts", headers=headers)
        self.assertEqual(memberships.status_code, 200, memberships.text)
        self.assertEqual(memberships.json(), [])

    def test_legacy_admin_login_and_profile_reads_create_no_customer_records(self):
        user = self.user(role="admin")
        before = self.customer_counts()
        for _ in range(2):
            body = self.login(user)
            self.assertIsNone(body["account"])
            self.assertIsNone(body["refresh_token"])
            self.assertEqual(body["user"]["name"], "")
            self.assert_empty_staff_reads(body)
        self.assertEqual(self.customer_counts(), before)

    def test_all_canonical_internal_roles_avoid_implicit_customer_onboarding(self):
        for role in InternalRole:
            with self.subTest(role=role.value):
                user = self.user(internal_role=role.value)
                before = self.customer_counts()
                body = self.login(user)
                self.assertIsNone(body["account"])
                self.assertEqual(body["user"]["role"], "cliente")
                self.assert_empty_staff_reads(body)
                self.assertEqual(self.customer_counts(), before)

    def test_inactive_internal_assignment_does_not_change_customer_login(self):
        user = self.user(internal_role="GV_OPERATIONS", active_assignment=False)
        body = self.login(user)
        self.assertIsNotNone(body["account"])
        self.assertEqual(body["account"]["customer_type"], "farm")
        self.assertEqual(self.customer_counts(), (1, 1, 1, 1, 1))

    def test_customer_login_still_creates_one_spanish_starter_workspace(self):
        user = self.user()
        first = self.login(user)
        second = self.login(user)
        self.assertEqual(first["account"]["id"], second["account"]["id"])
        self.assertEqual(self.customer_counts(), (1, 1, 1, 1, 1))
        company = self.db.query(Company).one()
        self.assertEqual(company.country, "Spain")
        self.assertEqual(company.timezone, "Europe/Madrid")

    def test_customer_registration_and_followup_login_preserve_explicit_profile(self):
        email = f"registered-{uuid.uuid4().hex}@example.com"
        response = self.client.post(
            "/auth/register",
            headers={"X-GeoVision-Client": "web"},
            json={
                "email": email,
                "password": PASSWORD,
                "full_name": "Spanish customer",
                "account_name": "Explicit site monitoring",
                "customer_type": "business",
                "sector_focus": "environment",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        registered = response.json()
        user = self.db.get(User, registered["user"]["id"])
        body = self.login(user)
        self.assertEqual(body["account"], registered["account"])
        self.assertEqual(body["account"]["customer_type"], "business")
        self.assertEqual(body["user"]["name"], "Spanish customer")
        self.assertEqual(self.customer_counts(), (1, 1, 1, 1, 1))

    def test_staff_existing_profile_and_workspace_are_preserved_without_repair(self):
        user = self.user(internal_role="GV_OPERATIONS")
        account = self.workspace(user)
        self.db.add(UserProfile(user_id=user.id, full_name="Existing staff name"))
        self.db.commit()
        before = self.customer_counts()
        body = self.login(user)
        self.assertEqual(body["account"]["id"], account.id)
        self.assertEqual(body["user"]["name"], "Existing staff name")
        self.assertEqual(self.customer_counts(), before)
        # No CompanyUser is inserted merely to repair a legacy workspace.
        self.assertEqual(self.db.query(CompanyUser).count(), 0)
        self.assertIsNone(account.onboarding_user_id)
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        response = self.client.get("/auth/me", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["account_id"], account.id)
        self.assertEqual(response.json()["customer_type"], "business")
        self.assertEqual(self.customer_counts(), before)

    def test_suspended_staff_membership_is_not_returned_or_repaired(self):
        user = self.user(internal_role="GV_SUPPORT")
        self.workspace(user, member_status="suspended")
        before = self.customer_counts()
        self.assertIsNone(self.login(user)["account"])
        self.assertEqual(self.customer_counts(), before)

    def test_archived_staff_workspace_is_not_returned_or_repaired(self):
        user = self.user(internal_role="GV_SUPPORT")
        self.workspace(user, account_status="archived")
        before = self.customer_counts()
        body = self.login(user)
        self.assertIsNone(body["account"])
        self.assert_empty_staff_reads(body)
        self.assertEqual(self.customer_counts(), before)

    def test_profile_default_uses_visible_workspace_after_archived_membership(self):
        user = self.user(internal_role="GV_SUPPORT")
        self.workspace(user, account_status="archived")
        visible = self.workspace(user)
        before = self.customer_counts()
        body = self.login(user)
        self.assertEqual(body["account"]["id"], visible.id)
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        response = self.client.get("/me", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["default_account_id"], visible.id)
        self.assertEqual([row["id"] for row in response.json()["accounts"]], [visible.id])
        self.assertEqual(self.customer_counts(), before)

    def test_staff_pending_invitation_is_unchanged_and_not_autoaccepted(self):
        user = self.user(internal_role="GV_SUPPORT")
        invitation = self.invite(user)
        before = self.customer_counts()
        self.assertIsNone(self.login(user)["account"])
        self.db.refresh(invitation)
        self.assertEqual(invitation.status, "pending")
        self.assertIsNone(invitation.accepted_by_user_id)
        self.assertEqual(self.customer_counts(), before)

    def test_staff_customer_membership_survives_another_pending_invitation(self):
        user = self.user(internal_role="GV_SUPPORT")
        account = self.workspace(user)
        invitation = self.invite(user)
        before = self.customer_counts()
        self.assertEqual(self.login(user)["account"]["id"], account.id)
        self.db.refresh(invitation)
        self.assertEqual(invitation.status, "pending")
        self.assertEqual(self.customer_counts(), before)

    def test_customer_pending_invitation_still_prevents_starter_workspace(self):
        user = self.user()
        invitation = self.invite(user)
        before = self.customer_counts()
        self.assertIsNone(self.login(user)["account"])
        self.assertEqual(self.customer_counts(), (before[0] + 1, *before[1:]))
        self.db.refresh(invitation)
        self.assertEqual(invitation.status, "pending")

    def test_native_staff_session_refresh_is_preserved_without_customer_records(self):
        user = self.user(role="admin")
        body = self.login(user, client="mobile")
        self.assertIsNotNone(body["refresh_token"])
        self.assertEqual(self.db.query(RefreshTokenFamily).count(), 1)
        refreshed = self.client.post(
            "/auth/refresh", json={"refresh_token": body["refresh_token"]}
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assert_empty_staff_reads(refreshed.json())
        self.assertEqual(self.customer_counts(), (0, 0, 0, 0, 0))

    def test_wrong_password_creates_no_customer_records_or_refresh_family(self):
        user = self.user(role="admin")
        self.login(user, password="Wrong-synthetic-password", expected_status=401)
        self.assertEqual(self.customer_counts(), (0, 0, 0, 0, 0))
        self.assertEqual(self.db.query(RefreshTokenFamily).count(), 0)

    def test_credential_snapshot_race_still_rolls_back_staff_session(self):
        user = self.user(role="admin")
        with self.assertRaises(auth.HTTPException) as raised:
            auth._build_auth_response(
                self.db,
                user,
                expected_password_hash="obsolete-synthetic-hash",
                expected_auth_generation=user.auth_generation,
                issue_refresh_token=True,
            )
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(self.customer_counts(), (0, 0, 0, 0, 0))
        self.assertEqual(self.db.query(RefreshTokenFamily).count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
