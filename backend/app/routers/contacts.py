"""Contact methods router — WhatsApp, Instagram, Email, Phone, SMS.

Public endpoint for frontend to fetch configured contact channels,
admin endpoint to manage them.
"""

from __future__ import annotations

from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import require_admin
from ..models import ContactMethod, User

router = APIRouter(prefix="/contacts", tags=["contacts"])


# ── Schemas ──

class ContactOut(BaseModel):
    id: str
    channel: str
    label: str
    value: str
    link: Optional[str] = None
    sort_order: int = 0

    model_config = {"from_attributes": True}


class ContactCreate(BaseModel):
    channel: str        # whatsapp, instagram, email, phone, sms
    label: str          # "Suporte", "Vendas", etc.
    value: str          # phone number, handle, email
    environment: str = "prod"
    is_public: bool = True
    sort_order: int = 0


# ── Default contact methods (seeded if table is empty) ──

DEFAULT_CONTACTS = [
    {"channel": "whatsapp", "label": "Suporte", "value": "+244928917269", "sort_order": 1},
    {"channel": "whatsapp", "label": "Vendas", "value": "+244928917269", "sort_order": 2},
    {"channel": "instagram", "label": "Instagram", "value": "Geovision.operations", "sort_order": 3},
    {"channel": "email", "label": "Suporte", "value": "support@geovisionops.com", "sort_order": 4},
    {"channel": "email", "label": "Vendas", "value": "sales@geovisionops.com", "sort_order": 5},
    {"channel": "email", "label": "Financeiro", "value": "finance@geovisionops.com", "sort_order": 6},
    {"channel": "email", "label": "Info", "value": "info@geovisionops.com", "sort_order": 7},
    {"channel": "phone", "label": "Telefone", "value": "+244928917269", "sort_order": 8},
]


def _build_link(channel: str, value: str, name: str = "", company: str = "", context: str = "") -> str:
    """Build the correct deep-link for each channel."""
    if channel == "whatsapp":
        # Build dynamic pre-filled message
        parts = ["Olá GeoVision"]
        if name:
            parts.append(f"sou {name}")
        if company:
            parts.append(f"da {company}")
        if context:
            parts.append(f"Preciso de suporte sobre {context}")
        else:
            parts.append("Preciso de ajuda")
        msg = ", ".join(parts) + "."
        phone = value.replace("+", "").replace(" ", "").replace("-", "")
        return f"https://wa.me/{phone}?text={quote(msg)}"
    elif channel == "instagram":
        handle = value.lstrip("@").strip()
        return f"https://instagram.com/{handle}"
    elif channel == "email":
        subject = quote("Contacto via GeoVision")
        body = quote(f"Olá,\n\nContacto via plataforma GeoVision.\n\nNome: {name}\nEmpresa: {company}\n\n")
        return f"mailto:{value}?subject={subject}&body={body}"
    elif channel == "phone":
        phone = value.replace(" ", "").replace("-", "")
        return f"tel:{phone}"
    elif channel == "sms":
        phone = value.replace(" ", "").replace("-", "")
        return f"sms:{phone}"
    return value


def _seed_defaults(db: Session):
    """Seed default contacts if table is empty, or fix stale values."""
    count = db.query(ContactMethod).count()
    if count == 0:
        # Fresh seed
        env = settings.env or "prod"
        for c in DEFAULT_CONTACTS:
            cm = ContactMethod(
                channel=c["channel"],
                label=c["label"],
                value=c["value"],
                environment=env,
                is_public=True,
                sort_order=c["sort_order"],
            )
            db.add(cm)
        try:
            db.commit()
        except Exception:
            db.rollback()
        return

    # Fix stale values from old domain / placeholder numbers
    _FIXES = {
        "geovision.digital": "geovisionops.com",
        "+244923000000": "+244928917269",
        "+244923000001": "+244928917269",
        "geovisionops": "Geovision.operations",  # instagram handle
    }
    rows = db.query(ContactMethod).all()
    changed = False
    for row in rows:
        for old_val, new_val in _FIXES.items():
            if old_val in row.value:
                row.value = row.value.replace(old_val, new_val)
                changed = True
    if changed:
        try:
            db.commit()
        except Exception:
            db.rollback()


# ── Public Endpoints ──

@router.get("/", response_model=List[ContactOut])
def list_contacts(
    name: str = "",
    company: str = "",
    context: str = "",
    db: Session = Depends(get_db),
):
    """List public contact methods with pre-built links.

    Query params name/company/context customize WhatsApp/email links.
    """
    _seed_defaults(db)

    env = settings.env or "prod"
    contacts = (
        db.query(ContactMethod)
        .filter(ContactMethod.is_public == True, ContactMethod.environment == env)
        .order_by(ContactMethod.sort_order)
        .all()
    )

    result = []
    for c in contacts:
        link = _build_link(c.channel, c.value, name=name, company=company, context=context)
        result.append(ContactOut(
            id=c.id, channel=c.channel, label=c.label,
            value=c.value, link=link, sort_order=c.sort_order,
        ))
    return result


# ── Admin Endpoints ──

@router.post("/", response_model=ContactOut, status_code=201)
def create_contact(
    payload: ContactCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cm = ContactMethod(
        channel=payload.channel,
        label=payload.label,
        value=payload.value,
        environment=payload.environment,
        is_public=payload.is_public,
        sort_order=payload.sort_order,
    )
    db.add(cm)
    db.commit()
    db.refresh(cm)

    link = _build_link(cm.channel, cm.value)
    return ContactOut(id=cm.id, channel=cm.channel, label=cm.label,
                      value=cm.value, link=link, sort_order=cm.sort_order)


@router.delete("/{contact_id}", status_code=204)
def delete_contact(
    contact_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cm = db.query(ContactMethod).filter(ContactMethod.id == contact_id).first()
    if not cm:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(cm)
    db.commit()
