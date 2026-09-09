import uuid

import pytest

from app.account_profiles import normalize_account_profile
from app.models import User
from app.oauth2 import create_access_token


@pytest.mark.parametrize(
    "customer_type,sector,entity,dashboard",
    [
        ("farm", "agro", "individual", "farm"),
        ("site", "environment", "individual", "site"),
        ("construction", "construction", "company", "construction"),
        ("business", "environment", "company", "business"),
        ("environment", "environment", "company", "environment"),
        ("industry", "industry", "company", "industry"),
        ("device", "environment", "individual", "device"),
        ("enterprise", "infrastructure", "company", "enterprise"),
    ],
)
def test_customer_profile_defaults(customer_type, sector, entity, dashboard):
    profile = normalize_account_profile(customer_type)
    assert profile["sector_focus"] == sector
    assert profile["entity_type"] == entity
    assert profile["dashboard_profile"] == dashboard
    assert profile["use_cases"]


@pytest.mark.parametrize(
    "customer_type,sector",
    [("farm", "solar"), ("site", "agro"), ("business", "mining"), ("enterprise", "demining")],
)
def test_out_of_scope_or_mismatched_sector_is_rejected(customer_type, sector):
    with pytest.raises(ValueError):
        normalize_account_profile(customer_type, sectors=[sector])


def test_legacy_sector_names_are_normalized_at_onboarding_boundary():
    assert normalize_account_profile("farm", sectors=["agriculture"])["sector_focus"] == "agro"
    assert normalize_account_profile("farm", sectors=["livestock"])["sector_focus"] == "agro"
    assert normalize_account_profile("industry", sectors=["mining"])["sector_focus"] == "industry"


def test_register_persists_enterprise_profile(client):
    email = f"profile-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "strong-pass-123",
            "customer_type": "enterprise",
            "sectors": ["infrastructure", "environment"],
            "sector_focus": "infrastructure",
            "use_cases": ["maintenance", "site_environment"],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["account"]["customer_type"] == "enterprise"
    assert body["account"]["dashboard_profile"] == "enterprise"
    assert body["account"]["entity_type"] == "company"
    assert body["account"]["sector_focus"] == "infrastructure,environment"
    assert body["account"]["use_cases"] == ["maintenance", "site_environment"]

    auth_me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert auth_me.status_code == 200, auth_me.text
    assert auth_me.json()["account"]["customer_type"] == "enterprise"
    assert auth_me.json()["account"]["dashboard_profile"] == "enterprise"
    assert auth_me.json()["account"]["sector_focus"] == "infrastructure,environment"

    me = client.get("/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200, me.text
    persisted = me.json()["accounts"][0]
    assert persisted["customer_type"] == "enterprise"
    assert persisted["dashboard_profile"] == "enterprise"
    assert persisted["use_cases"] == ["maintenance", "site_environment"]


def test_oauth_onboarding_creates_same_durable_profile(client, db_session):
    email = f"oauth-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email, password_hash=None, role="cliente", is_active=True)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token({"sub": email, "role": "cliente", "uid": user.id})

    response = client.post(
        "/auth/onboarding",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "customer_type": "site",
            "sectors": ["environment"],
            "sector_focus": "environment",
            "use_cases": ["air_quality", "water", "leaks"],
        },
    )
    assert response.status_code == 200, response.text
    account = response.json()["account"]
    assert account["customer_type"] == "site"
    assert account["dashboard_profile"] == "site"
    assert account["sector_focus"] == "environment"
    assert account["use_cases"] == ["air_quality", "water", "leaks"]
