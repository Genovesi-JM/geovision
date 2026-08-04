import uuid

from app.models import Company, CompanyUser, Site, User
from app.utils import hash_password


def _setup(client, db_session):
    email = f"insp-{uuid.uuid4().hex[:8]}@example.com"
    db_session.add(User(email=email, password_hash=hash_password("long-password-123"), role="cliente", is_active=True)); db_session.commit()
    company = Company(name="Insp Co", email=f"c-{uuid.uuid4().hex[:6]}@example.test"); db_session.add(company); db_session.flush()
    db_session.add(CompanyUser(company_id=company.id, email=email, name="Insp", role="owner", is_active=True))
    site = Site(company_id=company.id, name="Build Site", country="Angola", sector="infrastructure"); db_session.add(site); db_session.commit()
    token = client.post("/auth/login", json={"email": email, "password": "long-password-123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, site


def test_construction_qr_inspection_and_report(client, db_session):
    headers, site = _setup(client, db_session)
    asset = client.post("/iot/assets", headers=headers, json={
        "name": "Pillar A", "site_id": site.id, "asset_type": "structure", "latitude": -8.8, "longitude": 13.2,
    })
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]

    qr = client.get(f"/construction/assets/{asset_id}/qr.svg", headers=headers)
    assert qr.status_code == 200 and b"<svg" in qr.content

    insp = client.post("/construction/inspections", headers=headers, json={
        "asset_id": asset_id, "category": "structural", "result": "attention",
        "notes": "hairline crack near base", "checklist": {"cracks": True, "corrosion": False},
    })
    assert insp.status_code == 201, insp.text
    body = insp.json()
    assert body["result"] == "attention"
    assert body["latitude"] == -8.8 and body["longitude"] == 13.2  # inherited from asset
    assert body["checklist"] == {"cracks": True, "corrosion": False}

    assert len(client.get("/construction/inspections", headers=headers).json()) == 1
    assert len(client.get(f"/construction/assets/{asset_id}/inspections", headers=headers).json()) == 1

    pdf = client.get(f"/construction/assets/{asset_id}/report.pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_construction_tenant_isolation(client, db_session):
    headers_a, site_a = _setup(client, db_session)
    asset = client.post("/iot/assets", headers=headers_a, json={"name": "Beam", "site_id": site_a.id, "asset_type": "structure"}).json()
    headers_b, _ = _setup(client, db_session)
    # Another tenant cannot inspect or read this asset.
    assert client.get(f"/construction/assets/{asset['id']}/inspections", headers=headers_b).status_code == 404
    blocked = client.post("/construction/inspections", headers=headers_b, json={"asset_id": asset["id"], "result": "pass"})
    assert blocked.status_code == 404
