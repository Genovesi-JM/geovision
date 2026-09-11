from __future__ import annotations

import uuid

from app.core.tokens import create_user_access_token
from app.models import Company, Order, User


def _login_headers(client, email: str, password: str = "123456") -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _headers(user: User) -> dict[str, str]:
    token = create_user_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        auth_generation=user.auth_generation,
    )
    return {"Authorization": f"Bearer {token}"}


def _ensure_capability(client, headers: dict[str, str], code: str, category: str) -> None:
    existing = client.get("/operations/capabilities", headers=headers)
    assert existing.status_code == 200, existing.text
    if code in {row["code"] for row in existing.json()}:
        return
    created = client.post(
        "/operations/capabilities",
        headers=headers,
        json={
            "code": code,
            "name": code.replace("_", " ").title(),
            "category": category,
        },
    )
    assert created.status_code == 201, created.text


def test_operations_can_search_private_contractors_and_suppliers(client, db_session):
    admin_headers = _login_headers(client, "teste@admin.com")
    customer_headers = _login_headers(client, "teste@clientes.com")
    _ensure_capability(client, admin_headers, "RGB", "SENSOR")
    _ensure_capability(client, admin_headers, "RTK", "POSITIONING")
    _ensure_capability(client, admin_headers, "AGRICULTURE", "SECTOR")

    suffix = uuid.uuid4().hex[:8]
    contractor = client.post(
        "/operations/contractors",
        headers=admin_headers,
        json={
            "code": f"PILOT_{suffix}",
            "display_name": "Qualified Luanda survey resource",
            "resource_type": "PILOT",
            "country_code": "ao",
            "region": "Luanda",
            "service_area": ["Luanda", {"radius_km": 150}],
            "capability_codes": ["RGB", "RTK", "AGRICULTURE"],
            "certifications": [
                {"type": "pilot_licence", "reference": f"LIC-{suffix}"}
            ],
            "insurance": {"provider": "Qualified insurer", "valid_until": "2027-12-31"},
            "equipment": [{"type": "aircraft", "capabilities": ["RGB", "RTK"]}],
            "document_refs": [{"type": "licence", "document_id": f"DOC-{suffix}"}],
            "quality_score": 92.5,
            "internal_notes": "Private qualification note",
        },
    )
    assert contractor.status_code == 201, contractor.text
    assert contractor.json()["resource_type"] == "DRONE_OPERATOR"
    assert {row["code"] for row in contractor.json()["capabilities"]} == {
        "RGB",
        "RTK",
        "AGRICULTURE",
    }

    invalid_type = client.post(
        "/operations/contractors",
        headers=admin_headers,
        json={
            "code": f"UNKNOWN_{suffix}",
            "display_name": "Unknown resource type",
            "resource_type": "UNCONTROLLED_TYPE",
        },
    )
    assert invalid_type.status_code == 422

    suitable = client.get(
        "/operations/contractors?country_code=AO&region=luanda&capability=RTK",
        headers=admin_headers,
    )
    assert suitable.status_code == 200, suitable.text
    assert [row["id"] for row in suitable.json()] == [contractor.json()["id"]]

    supplier = client.post(
        "/catalog/internal/suppliers",
        headers=admin_headers,
        json={
            "code": f"SUP_{suffix}",
            "legal_name": "Private sensor source",
            "country_code": "AO",
            "region": "Luanda",
            "service_area": ["Angola"],
            "capabilities": ["SENSORS", "RTK"],
            "certifications": [{"type": "quality", "reference": f"Q-{suffix}"}],
            "insurance": {"valid_until": "2027-12-31"},
            "document_refs": [{"type": "due_diligence", "document_id": f"D-{suffix}"}],
            "quality_score": 88,
        },
    )
    assert supplier.status_code == 201, supplier.text
    found_supplier = client.get(
        "/catalog/internal/suppliers?region=luanda&capability=RTK",
        headers=admin_headers,
    )
    assert found_supplier.status_code == 200, found_supplier.text
    assert supplier.json()["id"] in {row["id"] for row in found_supplier.json()}

    updated_contractor = client.patch(
        f"/operations/contractors/{contractor.json()['id']}",
        headers=admin_headers,
        json={"availability": "LIMITED", "quality_score": 94},
    )
    assert updated_contractor.status_code == 200, updated_contractor.text
    assert updated_contractor.json()["availability"] == "LIMITED"
    assert (
        client.delete(
            f"/operations/contractors/{contractor.json()['id']}",
            headers=admin_headers,
        ).status_code
        == 204
    )
    contractor_detail = client.get(
        f"/operations/contractors/{contractor.json()['id']}", headers=admin_headers
    )
    assert contractor_detail.json()["status"] == "INACTIVE"

    assert (
        client.delete(
            f"/catalog/internal/suppliers/{supplier.json()['id']}",
            headers=admin_headers,
        ).status_code
        == 204
    )
    supplier_detail = client.get(
        f"/catalog/internal/suppliers/{supplier.json()['id']}", headers=admin_headers
    )
    assert supplier_detail.status_code == 200, supplier_detail.text
    assert supplier_detail.json()["status"] == "INACTIVE"

    assert client.get("/operations/contractors", headers=customer_headers).status_code == 403
    assert (
        client.get("/catalog/internal/suppliers", headers=customer_headers).status_code
        == 403
    )
    assert client.get("/catalog/items").status_code == 200
    assert client.get("/contractors").status_code == 404

    credential_payload = {
        "code": f"BAD_{suffix}",
        "display_name": "Unsafe resource",
        "resource_type": "TECHNICIAN",
        "insurance": {"api_key": "must-not-persist"},
    }
    rejected = client.post(
        "/operations/contractors", headers=admin_headers, json=credential_payload
    )
    assert rejected.status_code == 422


def test_contractor_sees_only_own_operational_assignment_surface(client, db_session):
    admin_headers = _login_headers(client, "teste@admin.com")
    _ensure_capability(client, admin_headers, "THERMAL", "SENSOR")

    contractor_user = User(
        email=f"contractor-{uuid.uuid4().hex}@example.com",
        role="client",
        is_active=True,
    )
    other_user = User(
        email=f"contractor-other-{uuid.uuid4().hex}@example.com",
        role="client",
        is_active=True,
    )
    organization = Company(
        name=f"Assignment customer {uuid.uuid4().hex[:8]}",
        email=f"assignment-{uuid.uuid4().hex}@example.com",
        status="active",
    )
    db_session.add_all([contractor_user, other_user, organization])
    db_session.flush()
    order = Order(
        company_id=organization.id,
        organization_id=organization.id,
        order_number=f"GV-2026-{uuid.uuid4().hex[:8].upper()}",
        order_type="SERVICE",
        status="paid",
        fulfilment_status="PAID",
        payment_status="PAID",
        currency="AOA",
        subtotal=1_250_000,
        total=1_250_000,
        internal_notes="Customer margin and billing must remain private",
    )
    db_session.add(order)
    db_session.commit()

    def create_profile(user: User, label: str) -> dict:
        response = client.post(
            "/operations/contractors",
            headers=admin_headers,
            json={
                "code": f"TECH_{uuid.uuid4().hex[:8]}",
                "user_id": user.id,
                "display_name": label,
                "resource_type": "FIELD_TECHNICIAN",
                "country_code": "AO",
                "region": "Bengo",
                "capability_codes": ["THERMAL"],
                "document_refs": [
                    {"type": "insurance", "document_id": f"DOC-{uuid.uuid4().hex[:8]}"}
                ],
                "internal_notes": "Operations-only performance note",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    contractor = create_profile(contractor_user, "Assigned technician")
    other_contractor = create_profile(other_user, "Unrelated technician")

    def create_assignment(contractor_id: str, title: str) -> dict:
        response = client.post(
            "/operations/assignments",
            headers=admin_headers,
            json={
                "contractor_id": contractor_id,
                "order_id": order.id,
                "title": title,
                "location": {"name": "Assigned field", "latitude": -8.84, "longitude": 13.23},
                "requirements": {"capabilities": ["THERMAL"], "safety_briefing": True},
                "upload_area": {"method": "platform-upload", "scope": title.lower().replace(" ", "-")},
                "required_documents": [{"type": "insurance", "status": "VALID"}],
                "agreed_cost_amount": 125_000,
                "cost_currency": "AOA",
                "internal_notes": "Supplier cost and margin are private",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    assignment = create_assignment(contractor["id"], "Thermal field inspection")
    unrelated = create_assignment(other_contractor["id"], "Unrelated customer job")

    scheduled = client.patch(
        f"/operations/assignments/{assignment['id']}",
        headers=admin_headers,
        json={
            "window_start": "2026-10-01T08:00:00Z",
            "window_end": "2026-10-01T12:00:00Z",
            "expected_version": assignment["lifecycle_version"],
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    assignment = scheduled.json()
    assert assignment["window_start"].startswith("2026-10-01T08:00:00")

    contractor_headers = _headers(contractor_user)
    other_headers = _headers(other_user)
    profile = client.get("/operations/contractor/me/profile", headers=contractor_headers)
    assert profile.status_code == 200, profile.text
    assert "internal_notes" not in profile.json()
    assert "quality_score" not in profile.json()

    own = client.get("/operations/contractor/me/assignments", headers=contractor_headers)
    assert own.status_code == 200, own.text
    assert [row["id"] for row in own.json()] == [assignment["id"]]
    safe_assignment = own.json()[0]
    forbidden = {
        "order_id",
        "fulfilment_job_id",
        "agreed_cost_amount",
        "cost_currency",
        "internal_notes",
        "assigned_by_user_id",
        "organization_id",
        "billing",
        "margin",
    }
    assert forbidden.isdisjoint(safe_assignment)
    assert safe_assignment["location"]["name"] == "Assigned field"
    assert safe_assignment["requirements"]["capabilities"] == ["THERMAL"]
    assert safe_assignment["upload_area"]["method"] == "platform-upload"

    assert (
        client.get(
            f"/operations/contractor/me/assignments/{unrelated['id']}",
            headers=contractor_headers,
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/operations/contractor/me/assignments/{assignment['id']}",
            headers=other_headers,
        ).status_code
        == 404
    )
    assert client.get("/operations/contractors", headers=contractor_headers).status_code == 403
    assert (
        client.get("/catalog/internal/suppliers", headers=contractor_headers).status_code
        == 403
    )

    accepted = client.post(
        f"/operations/contractor/me/assignments/{assignment['id']}/decision",
        headers=contractor_headers,
        json={"decision": "ACCEPTED", "expected_version": assignment["lifecycle_version"]},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"
    invalid_reversal = client.post(
        f"/operations/contractor/me/assignments/{assignment['id']}/decision",
        headers=contractor_headers,
        json={
            "decision": "DECLINED",
            "expected_version": accepted.json()["lifecycle_version"],
        },
    )
    assert invalid_reversal.status_code == 409

    customer_headers = _login_headers(client, "teste@clientes.com")
    assert (
        client.get("/operations/contractor/me/assignments", headers=customer_headers).status_code
        == 403
    )
