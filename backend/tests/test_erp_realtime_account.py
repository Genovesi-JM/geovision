import json

from app.database import SessionLocal
from app.models import AccountEvent, CompanyUser, IntegrationOutbox, Order, Payment
from app.services.erp_sync import enqueue_erp_event, process_pending, publish_account_event


def _login_headers(client, email="teste@clientes.com", password="123456"):
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _company_id():
    db = SessionLocal()
    try:
        membership = db.query(CompanyUser).filter_by(email="teste@clientes.com").first()
        assert membership is not None
        return membership.company_id
    finally:
        db.close()


def test_account_overview_is_customer_scoped(client):
    headers = _login_headers(client)
    company_id = _company_id()
    db = SessionLocal()
    try:
        owned = Payment(company_id=company_id, order_id="owned", amount=125000, currency="AOA", provider="mock", status="pending")
        foreign = Payment(company_id="another-company", order_id="foreign", amount=999999, currency="AOA", provider="mock", status="pending")
        db.add_all([owned, foreign])
        db.commit()
    finally:
        db.close()

    response = client.get("/mobile/account/overview", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organisation"]["id"] == company_id
    assert body["financial"]["outstanding_cents"] == 125000
    assert body["financial"]["pending_payments"] == 1


def test_account_events_are_tenant_isolated(client):
    headers = _login_headers(client)
    company_id = _company_id()
    db = SessionLocal()
    try:
        publish_account_event(db, company_id=company_id, event_type="order.updated", resource_type="order", resource_id="one", title="Owned")
        publish_account_event(db, company_id="another-company", event_type="order.updated", resource_type="order", resource_id="two", title="Foreign")
        db.commit()
    finally:
        db.close()

    response = client.get("/mobile/account/events", headers=headers)
    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert "Owned" in titles
    assert "Foreign" not in titles


def test_erp_outbox_is_idempotent_and_mock_processes():
    db = SessionLocal()
    try:
        first = enqueue_erp_event(db, company_id="c1", aggregate_type="order", aggregate_id="o1", event_type="order.created", payload={"currency": "AOA"}, version="1")
        db.commit()
        second = enqueue_erp_event(db, company_id="c1", aggregate_type="order", aggregate_id="o1", event_type="order.created", payload={"currency": "AOA"}, version="1")
        assert second.id == first.id
        result = process_pending(db)
        db.refresh(first)
        assert result["failed"] == 0
        assert first.status == "completed"
        assert first.external_id.startswith("MOCK-SALES ORDER-")
        assert db.query(IntegrationOutbox).filter_by(idempotency_key=first.idempotency_key).count() == 1
    finally:
        db.close()
