"""Regression checks for the Spain-first launch baseline."""

from app.models import Cart, Company, Site
from app.modules.orders.schemas import CheckoutRequest, DraftOrderCreate
from app.modules.organizations.schemas import OrganizationCreate, WorkspaceCreate


def test_customer_creation_defaults_to_spain_and_madrid_timezone():
    request = OrganizationCreate(
        name="GeoVision España Demo",
        workspace=WorkspaceCreate(name="Finca Madrid Norte"),
    )

    assert request.country == "Spain"
    assert request.timezone == "Europe/Madrid"
    assert Company.__table__.c.country.default.arg == "Spain"
    assert Company.__table__.c.timezone.default.arg == "Europe/Madrid"
    assert Site.__table__.c.country.default.arg == "Spain"


def test_new_commerce_flows_default_to_eur():
    checkout = CheckoutRequest(
        payment_method="visa_mastercard",
        billing_info={"country": "ES"},
    )
    draft = DraftOrderCreate(
        organization_id="org-spain",
        items=[{"catalog_item_id": "service-demo"}],
    )

    assert checkout.currency == "EUR"
    assert draft.currency == "EUR"
    assert Cart.__table__.c.currency.default.arg == "EUR"
