import uuid

import pytest
from fastapi import HTTPException

from app.account_profiles import normalize_account_profile
from app.models import Account, AccountMember, Company, User
from app.oauth2 import create_access_token
from app.routers.auth import _ensure_company


@pytest.mark.parametrize(
    "customer_type,sector,entity,dashboard",
    [
        ("farm", "agriculture", "individual", "farm"),
        ("site", "environment", "individual", "site"),
        (
            "construction",
            "construction_infrastructure",
            "company",
            "construction",
        ),
        ("business", "environment", "company", "business"),
        ("environment", "environment", "company", "environment"),
        (
            "industry",
            "industry_energy_utilities",
            "company",
            "industry",
        ),
        ("mining", "mining", "company", "mining"),
        ("ports_logistics", "ports_logistics", "company", "ports_logistics"),
        ("device", "environment", "individual", "device"),
        (
            "enterprise",
            "construction_infrastructure",
            "company",
            "enterprise",
        ),
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
    [
        ("farm", "solar"),
        ("site", "agro"),
        ("construction", "mining"),
        ("enterprise", "demining"),
    ],
)
def test_out_of_scope_or_mismatched_sector_is_rejected(customer_type, sector):
    with pytest.raises(ValueError):
        normalize_account_profile(customer_type, sectors=[sector])


def test_legacy_sector_names_are_normalized_at_onboarding_boundary():
    assert (
        normalize_account_profile("farm", sectors=["agro"])["sector_focus"]
        == "agriculture"
    )
    assert (
        normalize_account_profile("farm", sectors=["livestock"])["sector_focus"]
        == "agriculture"
    )
    assert (
        normalize_account_profile("construction", sectors=["infrastructure"])[
            "sector_focus"
        ]
        == "construction_infrastructure"
    )
    assert (
        normalize_account_profile("industry", sectors=["industry"])["sector_focus"]
        == "industry_energy_utilities"
    )
    assert (
        normalize_account_profile("ports_logistics", sectors=["ports_industrial"])[
            "sector_focus"
        ]
        == "ports_logistics"
    )
    assert (
        normalize_account_profile("mining", sectors=["mining"])["sector_focus"]
        == "mining"
    )


def test_industrial_operations_profile_preserves_three_distinct_sector_choices():
    profile = normalize_account_profile(
        "industry", sectors=["industry", "mining", "ports"]
    )

    assert profile["sectors"] == [
        "industry_energy_utilities",
        "mining",
        "ports_logistics",
    ]


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
            "modules_enabled": [
                "assets",
                "construction",
                "environment",
                "ports_industrial",
            ],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["account"]["customer_type"] == "enterprise"
    assert body["account"]["dashboard_profile"] == "enterprise"
    assert body["account"]["entity_type"] == "company"
    assert body["account"]["sector_focus"] == "construction_infrastructure,environment"
    assert body["account"]["use_cases"] == ["maintenance", "site_environment"]

    headers = {"Authorization": f"Bearer {body['access_token']}"}
    auth_me = client.get("/auth/me", headers=headers)
    assert auth_me.status_code == 200, auth_me.text
    assert auth_me.json()["account"]["customer_type"] == "enterprise"
    assert auth_me.json()["account"]["dashboard_profile"] == "enterprise"
    assert (
        auth_me.json()["account"]["sector_focus"]
        == "construction_infrastructure,environment"
    )

    me = client.get("/me", headers=headers)
    assert me.status_code == 200, me.text
    persisted = me.json()["accounts"][0]
    assert persisted["customer_type"] == "enterprise"
    assert persisted["dashboard_profile"] == "enterprise"
    assert persisted["use_cases"] == ["maintenance", "site_environment"]
    assert persisted["modules_enabled"] == [
        "assets",
        "infrastructure",
        "environmental",
        "ports_logistics",
    ]

    for path in ("/kpi/summary", "/kpi/alerts", "/kpi/context"):
        invalid = client.get(path, params={"sector": "future"}, headers=headers)
        assert invalid.status_code == 422, invalid.text
        unauthorized = client.get(path, params={"sector": "mining"}, headers=headers)
        assert unauthorized.status_code == 403, unauthorized.text

    filtered_summary = client.get(
        "/kpi/summary",
        params={"sector": "infrastructure"},
        headers=headers,
    )
    assert filtered_summary.status_code == 200, filtered_summary.text
    assert filtered_summary.json()["sector"] == "construction_infrastructure"
    filtered_context = client.get(
        "/kpi/context",
        params={"sector": "infrastructure"},
        headers=headers,
    )
    assert filtered_context.status_code == 200, filtered_context.text
    assert filtered_context.json()["active_sector"] == "construction_infrastructure"
    assert filtered_context.json()["alerts_availability"] == "NO_DATA"
    assert filtered_context.json()["services_count"] is None
    assert filtered_context.json()["hardware_count"] is None
    assert "sem fonte de dados ligada" in filtered_context.json()["summary_text"]

    alerts = client.get("/kpi/alerts", headers=headers)
    assert alerts.status_code == 200, alerts.text
    assert alerts.json()["availability"] == "NO_DATA"
    details = client.get("/kpi/details", headers=headers)
    assert details.status_code == 200, details.text
    assert all(item["value"] == "—" for item in details.json()["items"])
    assert all(item["status"] is None for item in details.json()["items"])


def test_account_entrypoints_bound_sector_selection_payloads(client):
    too_long = "future," * 80
    register = client.post(
        "/auth/register",
        json={
            "email": f"bounded-{uuid.uuid4().hex[:8]}@example.com",
            "password": "strong-pass-123",
            "sector_focus": too_long,
        },
    )
    assert register.status_code == 422

    too_many = ["agriculture"] * 7
    register_list = client.post(
        "/auth/register",
        json={
            "email": f"bounded-list-{uuid.uuid4().hex[:8]}@example.com",
            "password": "strong-pass-123",
            "sectors": too_many,
        },
    )
    assert register_list.status_code == 422

    oversized_item = client.post(
        "/auth/register",
        json={
            "email": f"bounded-item-{uuid.uuid4().hex[:8]}@example.com",
            "password": "strong-pass-123",
            "sectors": ["x" * 321],
        },
    )
    assert oversized_item.status_code == 422


def test_legacy_unknown_sector_cannot_seed_a_new_company(db_session):
    user = User(
        email=f"legacy-sector-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=None,
        role="cliente",
        is_active=True,
    )
    organization = Company(
        name="Legacy sector holder",
        email=f"legacy-company-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add_all([user, organization])
    db_session.flush()
    account = Account(
        organization_id=organization.id,
        name="Legacy unknown workspace",
        sector_focus="future_special",
        entity_type="company",
        customer_type="business",
        dashboard_profile="business",
    )
    db_session.add(account)
    db_session.flush()
    db_session.add(
        AccountMember(
            account_id=account.id,
            user_id=user.id,
            role="owner",
            status="active",
        )
    )
    db_session.commit()
    company_count = db_session.query(Company).count()

    with pytest.raises(HTTPException) as error:
        _ensure_company(db_session, user, account.name, account.sector_focus)

    assert error.value.status_code == 409
    assert db_session.query(Company).count() == company_count


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
