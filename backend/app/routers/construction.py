"""Construction reporting + QR asset inspections.

Reuses the existing ``IotAsset`` as the QR-taggable, inspectable asset. A technician
scans an asset's QR (which deep-links to an inspection form), logs an inspection, and
GeoVision produces a PDF inspection report. No new app — this rides on the existing
auth, tenants, sites and assets.
"""
from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import AssetInspection, AuditLog, Company, IotAsset, Site, User
from app.routers.me import _get_user_company_id

router = APIRouter(prefix="/construction", tags=["construction"])


def _company_id(user: User, db: Session) -> str:
    value = _get_user_company_id(user, db)
    if not value:
        raise HTTPException(status_code=409, detail="Create or link a customer organisation first")
    return value


def _asset_for_company(db: Session, asset_id: str, company_id: str) -> IotAsset:
    asset = db.get(IotAsset, asset_id)
    if not asset or asset.company_id != company_id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


class InspectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: str
    category: str = Field(default="general", max_length=80)
    result: Literal["pass", "attention", "fail"] = "pass"
    notes: str | None = Field(default=None, max_length=4000)
    checklist: dict[str, bool] = Field(default_factory=dict)
    photos: list[str] = Field(default_factory=list, max_length=40)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


def _inspection_payload(row: AssetInspection) -> dict:
    return {
        "id": row.id, "asset_id": row.asset_id, "site_id": row.site_id,
        "category": row.category, "result": row.result, "notes": row.notes,
        "inspector_name": row.inspector_name, "checklist": json.loads(row.checklist_json or "{}"),
        "photos": json.loads(row.photos_json or "[]"),
        "latitude": row.latitude, "longitude": row.longitude,
        "created_at": row.created_at.isoformat() + "Z",
    }


@router.post("/inspections", status_code=status.HTTP_201_CREATED)
def create_inspection(payload: InspectionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    asset = _asset_for_company(db, payload.asset_id, company_id)
    row = AssetInspection(
        company_id=company_id, asset_id=asset.id, site_id=asset.site_id,
        inspected_by=user.id, inspector_name=(user.email or "").split("@")[0],
        category=payload.category, result=payload.result, notes=payload.notes,
        checklist_json=json.dumps(payload.checklist), photos_json=json.dumps(payload.photos),
        latitude=payload.latitude if payload.latitude is not None else asset.latitude,
        longitude=payload.longitude if payload.longitude is not None else asset.longitude,
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.add(AuditLog(user_id=user.id, user_email=user.email, action="construction.inspection_created",
                    resource_type="asset_inspection", resource_id=asset.id,
                    details=json.dumps({"result": payload.result, "category": payload.category})))
    db.commit(); db.refresh(row)
    return _inspection_payload(row)


@router.get("/inspections")
def list_inspections(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    rows = (db.query(AssetInspection)
            .filter(AssetInspection.company_id == company_id)
            .order_by(AssetInspection.created_at.desc()).limit(500).all())
    return [_inspection_payload(r) for r in rows]


@router.get("/assets/{asset_id}/inspections")
def asset_inspections(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    _asset_for_company(db, asset_id, company_id)
    rows = (db.query(AssetInspection)
            .filter(AssetInspection.company_id == company_id, AssetInspection.asset_id == asset_id)
            .order_by(AssetInspection.created_at.desc()).all())
    return [_inspection_payload(r) for r in rows]


@router.get("/assets/{asset_id}/qr.svg")
def asset_qr(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    asset = _asset_for_company(db, asset_id, company_id)
    import qrcode
    import qrcode.image.svg
    url = f"{settings.frontend_base}/inspect.html?asset={asset.id}&site={asset.site_id}"
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage, box_size=10, border=2)
    buf = BytesIO(); img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml",
                    headers={"Content-Disposition": f'inline; filename="asset-{asset.id}-qr.svg"'})


@router.get("/assets/{asset_id}/report.pdf")
def inspection_report(asset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    company_id = _company_id(user, db)
    asset = _asset_for_company(db, asset_id, company_id)
    rows = (db.query(AssetInspection)
            .filter(AssetInspection.company_id == company_id, AssetInspection.asset_id == asset_id)
            .order_by(AssetInspection.created_at).all())
    site = db.get(Site, asset.site_id); company = db.get(Company, company_id)
    content = _build_inspection_pdf(asset, site, company, rows)
    return Response(content=content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="asset-{asset.id}-inspections.pdf"'})


def _build_inspection_pdf(asset, site, company, inspections) -> bytes:
    from reportlab.platypus import Paragraph, Spacer
    from app.iot.reports import report_doc, meta_table, data_table

    output, doc, styles = report_doc(f"GeoVision inspection report — {asset.name}")
    counts = {"pass": 0, "attention": 0, "fail": 0}
    for i in inspections:
        counts[i.result] = counts.get(i.result, 0) + 1
    story = [
        Paragraph("GeoVision Field Inspection Report", styles["Title"]),
        Paragraph(f"Asset · {asset.name}", styles["Heading2"]), Spacer(1, 6),
        meta_table([
            ["Customer", company.name if company else asset.company_id],
            ["Site", site.name if site else asset.site_id],
            ["Asset type", asset.asset_type],
            ["Inspections", str(len(inspections))],
            ["Pass / Attention / Fail", f"{counts.get('pass',0)} / {counts.get('attention',0)} / {counts.get('fail',0)}"],
            ["Generated", datetime.utcnow().isoformat() + "Z"],
        ]),
        Spacer(1, 12), Paragraph("Inspection timeline", styles["Heading2"]),
    ]
    table = [["Date", "Category", "Result", "Inspector", "Notes"]]
    for i in inspections:
        table.append([i.created_at.strftime("%Y-%m-%d %H:%M"), i.category, i.result,
                      i.inspector_name or "—", (i.notes or "")[:70]])
    story.append(data_table(table, col_mm=(30, 26, 20, 28, 58), font_size=7))
    doc.build(story)
    return output.getvalue()
