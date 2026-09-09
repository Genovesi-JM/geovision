# app/routers/orders.py
import json
import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app.core.time import utc_now
from app.models import CatalogItem, User, Order, OrderItem, Product, Inventory

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("")
def create_order(
    items: List[Dict],
    shipping_address: Optional[Dict] = None,
    notes: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not items:
        raise HTTPException(status_code=400, detail="Carrinho vazio")

    subtotal = 0.0
    order_items: List[OrderItem] = []

    for it in items:
        pid = it.get("product_id")
        qty = int(it.get("qty", 0))
        if not pid or qty <= 0:
            raise HTTPException(status_code=400, detail="Item inválido")

        p = db.get(Product, pid)
        if not p or not p.is_active:
            raise HTTPException(status_code=404, detail="Produto não encontrado")

        inv = db.get(Inventory, pid)
        available = (inv.qty_on_hand - inv.qty_reserved) if inv else 0
        if qty > available:
            raise HTTPException(status_code=409, detail=f"Sem stock para {p.name}")

        unit_price = float(p.price)
        line_total = unit_price * qty
        subtotal += line_total

        if inv:
            inv.qty_reserved += qty

        catalog_item = (
            db.query(CatalogItem)
            .filter(CatalogItem.legacy_source_id == p.id)
            .first()
        )
        order_items.append(OrderItem(
            product_id=p.id,
            catalog_item_id=catalog_item.id if catalog_item else None,
            sku=p.sku,
            name=p.name,
            product_type="physical",
            catalog_item_type="PHYSICAL_PRODUCT",
            currency=p.currency or "AOA",
            unit_price=unit_price,
            qty=qty,
            line_total=line_total,
            pricing_snapshot_json=json.dumps(
                {
                    "catalog_item_id": catalog_item.id if catalog_item else None,
                    "code": p.sku,
                    "name": p.name,
                    "item_type": "PHYSICAL_PRODUCT",
                    "currency": p.currency or "AOA",
                    "unit_amount": int(unit_price),
                    "quantity": qty,
                    "captured_at": utc_now().isoformat(),
                },
                sort_keys=True,
            ),
            fulfilment_hints_json=json.dumps(
                {"fulfilment_type": "PHYSICAL_SHIPMENT"}, sort_keys=True
            ),
        ))

    context = getattr(user, "_authorization_context", None)
    now = utc_now()
    o = Order(
        user_id=user.id,
        company_id=getattr(context, "active_organization_id", None),
        organization_id=getattr(context, "active_organization_id", None),
        workspace_id=getattr(context, "active_workspace_id", None),
        order_number=f"GV-{now.year}-{uuid.uuid4().hex[:8].upper()}",
        order_type="PHYSICAL",
        fulfilment_status="CONFIRMED",
        payment_status="PENDING",
        confirmed_at=now,
        status="pending",
        currency="AOA",
        subtotal=subtotal,
        shipping_fee=0,
        discount_total=0,
        total=subtotal,
        shipping_address_json=json.dumps(shipping_address or {}),
        notes=notes,
    )
    db.add(o)
    db.flush()

    for oi in order_items:
        oi.order_id = o.id
        db.add(oi)

    db.commit()
    return {"order_id": o.id, "total": float(o.total), "status": o.status}

@router.get("")
def list_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Order)
    if user.role != "admin":
        q = q.filter(Order.user_id == user.id)
    orders = q.order_by(Order.created_at.desc()).all()
    return [{"id": o.id, "status": o.status, "total": float(o.total), "created_at": o.created_at.isoformat()} for o in orders]
