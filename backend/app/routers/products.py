# app/routers/products.py
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Product, ProductImage, Inventory, Category

router = APIRouter(prefix="/products", tags=["products"])

@router.get("")
def list_products(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active == True).all()
    out = []
    for p in products:
        primary = next((img.url for img in p.images if img.is_primary), None)
        out.append({
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "description": p.description,
            "price": float(p.price),
            "currency": p.currency,
            "image": primary,
            "qty_on_hand": p.inventory.qty_on_hand if p.inventory else 0,
            "category": p.category.name if p.category else None,
        })
    return out

@router.post("")
def create_product(
    sku: str,
    name: str,
    price: float,
    category_slug: Optional[str] = None,
    image_url: Optional[str] = None,
    qty_on_hand: int = 0,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    cat_id = None
    if category_slug:
        cat = db.query(Category).filter(Category.slug == category_slug).first()
        if cat:
            cat_id = cat.id

    p = Product(sku=sku, name=name, price=price, category_id=cat_id)
    db.add(p)
    db.flush()

    db.add(Inventory(product_id=p.id, qty_on_hand=qty_on_hand))
    if image_url:
        db.add(ProductImage(product_id=p.id, url=image_url, is_primary=True))

    db.commit()
    return {"id": p.id}
