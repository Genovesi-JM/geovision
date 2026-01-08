# app/routers/orders.py
import json
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, Order, OrderItem, Product, Inventory

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

        order_items.append(OrderItem(
            product_id=p.id,
            sku=p.sku,
            name=p.name,
            unit_price=unit_price,
            qty=qty,
            line_total=line_total
        ))

    o = Order(
        user_id=user.id,
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
