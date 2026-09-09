from __future__ import annotations

import uuid

from app.core.tokens import create_user_access_token
from app.models import (
    Company,
    FulfilmentJob,
    OperationalDomainEvent,
    Order,
    OrderItem,
    User,
)


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


def _service_order(db_session) -> tuple[Order, User]:
    customer = (
        db_session.query(User).filter(User.email == "teste@clientes.com").one()
    )
    organization = Company(
        name=f"Fulfilment customer {uuid.uuid4().hex[:8]}",
        email=f"fulfilment-{uuid.uuid4().hex}@example.com",
        status="active",
    )
    db_session.add(organization)
    db_session.flush()
    order = Order(
        user_id=customer.id,
        company_id=organization.id,
        organization_id=organization.id,
        order_number=f"GV-2026-{uuid.uuid4().hex[:8].upper()}",
        order_type="SERVICE",
        status="paid",
        fulfilment_status="PAID",
        payment_status="PAID",
        currency="AOA",
        subtotal=1_000_000,
        total=1_000_000,
        internal_notes="Margin and supplier details are internal",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        OrderItem(
            order_id=order.id,
            sku="FIELD-SURVEY",
            name="Field survey and report",
            catalog_item_type="SERVICE",
            product_type="service",
            currency="AOA",
            unit_price=1_000_000,
            qty=1,
            line_total=1_000_000,
            fulfilment_hints_json='{"fulfilment_type":"FIELD_SERVICE"}',
        )
    )
    db_session.commit()
    return order, customer


def test_service_order_plans_dependency_chain_and_safe_views(client, db_session):
    admin_headers = _login_headers(client, "teste@admin.com")
    customer_headers = _login_headers(client, "teste@clientes.com")
    order, _ = _service_order(db_session)

    planned = client.post(
        f"/operations/jobs/plan-order/{order.id}", headers=admin_headers
    )
    assert planned.status_code == 200, planned.text
    payload = planned.json()
    assert payload["created_count"] == 4
    assert payload["existing_count"] == 0
    assert [job["job_type"] for job in payload["jobs"]] == [
        "FLIGHT_CAPTURE",
        "PROCESS_DATA",
        "ANALYST_REVIEW",
        "PUBLISH_REPORT",
    ]
    assert payload["jobs"][0]["state"] == "READY"
    assert [job["state"] for job in payload["jobs"][1:]] == [
        "BLOCKED",
        "BLOCKED",
        "BLOCKED",
    ]
    for index in range(1, 4):
        assert payload["jobs"][index]["dependencies"][0]["job_id"] == payload["jobs"][
            index - 1
        ]["id"]

    planned_again = client.post(
        f"/operations/jobs/plan-order/{order.id}", headers=admin_headers
    )
    assert planned_again.status_code == 200, planned_again.text
    assert planned_again.json()["created_count"] == 0
    assert planned_again.json()["existing_count"] == 4
    assert db_session.query(FulfilmentJob).filter(FulfilmentJob.order_id == order.id).count() == 4

    progress = client.get(f"/orders/{order.id}/progress", headers=customer_headers)
    assert progress.status_code == 200, progress.text
    assert progress.json()["total_steps"] == 4
    assert progress.json()["status"] == "preparing"
    serialized = progress.text.lower()
    for secret_name in (
        "contractor",
        "assigned_user",
        "direct_cost",
        "cost_currency",
        "cost_reference",
        "internal_notes",
    ):
        assert secret_name not in serialized
    assert client.get("/operations/jobs", headers=customer_headers).status_code == 403


def test_job_state_rules_contractor_scope_and_local_events(client, db_session):
    admin_headers = _login_headers(client, "teste@admin.com")
    order, _ = _service_order(db_session)
    planned = client.post(
        f"/operations/jobs/plan-order/{order.id}", headers=admin_headers
    ).json()["jobs"]
    flight, process = planned[0], planned[1]

    contractor_user = User(
        email=f"job-contractor-{uuid.uuid4().hex}@example.com",
        role="client",
        is_active=True,
    )
    db_session.add(contractor_user)
    db_session.commit()
    profile = client.post(
        "/operations/contractors",
        headers=admin_headers,
        json={
            "code": f"JOB_{uuid.uuid4().hex[:8]}",
            "user_id": contractor_user.id,
            "display_name": "Assigned field crew",
            "resource_type": "PILOT",
        },
    )
    assert profile.status_code == 201, profile.text
    contractor_id = profile.json()["id"]

    assigned_flight = client.patch(
        f"/operations/jobs/{flight['id']}/assignment",
        headers=admin_headers,
        json={
            "contractor_id": contractor_id,
            "expected_version": flight["lifecycle_version"],
        },
    )
    assert assigned_flight.status_code == 200, assigned_flight.text
    flight = assigned_flight.json()
    assert flight["state"] == "ASSIGNED"
    db_job = db_session.get(FulfilmentJob, flight["id"])
    db_job.direct_cost_amount = 175_000
    db_job.cost_currency = "AOA"
    db_session.commit()

    admin = db_session.query(User).filter(User.email == "teste@admin.com").one()
    assigned_process = client.patch(
        f"/operations/jobs/{process['id']}/assignment",
        headers=admin_headers,
        json={
            "user_id": admin.id,
            "expected_version": process["lifecycle_version"],
        },
    )
    assert assigned_process.status_code == 200, assigned_process.text
    process = assigned_process.json()
    assert process["state"] == "BLOCKED"
    premature = client.patch(
        f"/operations/jobs/{process['id']}/state",
        headers=admin_headers,
        json={"state": "IN_PROGRESS", "expected_version": process["lifecycle_version"]},
    )
    assert premature.status_code == 409
    assert premature.json()["detail"]["code"] == "dependency_incomplete"

    started = client.patch(
        f"/operations/jobs/{flight['id']}/state",
        headers=admin_headers,
        json={"state": "IN_PROGRESS", "expected_version": flight["lifecycle_version"]},
    )
    assert started.status_code == 200, started.text
    completed = client.patch(
        f"/operations/jobs/{flight['id']}/state",
        headers=admin_headers,
        json={
            "state": "COMPLETED",
            "expected_version": started.json()["lifecycle_version"],
        },
    )
    assert completed.status_code == 200, completed.text
    process_now = client.get(
        f"/operations/jobs/{process['id']}", headers=admin_headers
    ).json()
    assert process_now["state"] == "ASSIGNED"

    process_started = client.patch(
        f"/operations/jobs/{process['id']}/state",
        headers=admin_headers,
        json={
            "state": "IN_PROGRESS",
            "expected_version": process_now["lifecycle_version"],
        },
    )
    assert process_started.status_code == 200, process_started.text
    invalid_reversal = client.patch(
        f"/operations/jobs/{flight['id']}/state",
        headers=admin_headers,
        json={
            "state": "IN_PROGRESS",
            "expected_version": completed.json()["lifecycle_version"],
        },
    )
    assert invalid_reversal.status_code == 409
    cycle = client.post(
        f"/operations/jobs/{flight['id']}/dependencies",
        headers=admin_headers,
        json={"depends_on_job_id": planned[-1]["id"]},
    )
    assert cycle.status_code == 409
    assert cycle.json()["detail"]["code"] == "dependency_cycle"

    contractor_headers = _headers(contractor_user)
    own = client.get("/operations/contractor/me/jobs", headers=contractor_headers)
    assert own.status_code == 200, own.text
    assert [job["id"] for job in own.json()] == [flight["id"]]
    contractor_payload = own.text.lower()
    for internal_name in (
        "order_id",
        "assigned_contractor_id",
        "assigned_user_id",
        "direct_cost",
        "cost_currency",
        "cost_reference",
        "plan_key",
        "source_order_item_id",
        "source_catalog_item_id",
    ):
        assert internal_name not in contractor_payload

    event_types = {
        row.event_type for row in db_session.query(OperationalDomainEvent).all()
    }
    assert {
        "fulfilment_job.created",
        "fulfilment_job.dependency_added",
        "fulfilment_job.assignment_changed",
        "fulfilment_job.state_changed",
        "fulfilment_job.dependencies_satisfied",
    }.issubset(event_types)
