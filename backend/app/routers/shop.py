"""
Shop Router

E-commerce endpoints for:
- Product catalog
- Cart operations
- Checkout
- Order management
- Customer profile (Minhas Compras)
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from pydantic import BaseModel, Field

from app.deps import get_current_user, get_optional_user, require_admin
from app.models import User
from sqlalchemy.orm import Session
from app.deps import get_db
from app.services.cart import get_cart_service, get_sector_labels
from app.services.orders import get_order_service, OrderStatus, PaymentMethod, EventType

logger = logging.getLogger(__name__)

# Products are seeded via main.py startup

router = APIRouter(prefix="/shop", tags=["Shop"])


# ============ SCHEMAS ============

# Cart
class AddToCartRequest(BaseModel):
    product_id: str
    quantity: int = 1
    scheduled_date: Optional[str] = None
    custom_options: Optional[dict] = None
    currency: Optional[str] = None


class UpdateCartItemRequest(BaseModel):
    quantity: int


class UpdateCurrencyRequest(BaseModel):
    currency: str = Field(..., description="AOA, USD, or EUR")


class ApplyCouponRequest(BaseModel):
    code: str


class SetDeliveryRequest(BaseModel):
    delivery_method: str


class SetSiteRequest(BaseModel):
    site_id: str


class CartItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_type: str
    sku: Optional[str]
    quantity: int
    unit_price: int
    total_price: int
    tax_rate: float
    tax_amount: int
    scheduled_date: Optional[str]
    custom_options: dict


class CartResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    company_id: Optional[str] = None
    site_id: Optional[str] = None
    items: List[CartItemResponse]
    subtotal: int
    discount_amount: int
    coupon_code: Optional[str] = None
    tax_rate: float
    tax_amount: int
    delivery_cost: int
    delivery_method: Optional[str]
    total: int
    currency: str
    item_count: int


# Checkout
class BillingInfo(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    company_name: Optional[str] = None
    nif: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "AO"


class CheckoutRequest(BaseModel):
    payment_method: str = Field(..., description="multicaixa_express, visa_mastercard, iban_angola, iban_international, paypal")
    currency: str = Field(default="AOA", description="AOA, USD, or EUR")
    billing_info: BillingInfo
    customer_notes: Optional[str] = None


class CheckoutResponse(BaseModel):
    success: bool
    order_id: Optional[str]
    order_number: Optional[str]
    payment_required: bool
    payment_method: Optional[str]
    payment_data: Optional[dict]
    error: Optional[str]


# Orders
class OrderItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    product_type: str
    quantity: int
    unit_price: int
    total_price: int
    status: str


class OrderEventResponse(BaseModel):
    id: str
    event_type: str
    title: str
    description: Optional[str]
    actor_name: Optional[str]
    is_customer_visible: bool
    created_at: str


class DeliverableResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    deliverable_type: str
    file_size: Optional[int]
    mime_type: Optional[str]
    download_url: Optional[str]
    is_ready: bool
    created_at: str


class OrderResponse(BaseModel):
    id: str
    order_number: str
    status: str
    status_label: str
    payment_method: Optional[str]
    payment_reference: Optional[str]
    currency: str
    subtotal: int
    discount_amount: int
    coupon_code: Optional[str]
    tax_amount: int
    delivery_cost: int
    total: int
    items: List[OrderItemResponse]
    events: List[OrderEventResponse]
    deliverables: List[DeliverableResponse]
    delivery_method: Optional[str]
    assigned_team: Optional[str]
    scheduled_start: Optional[str]
    estimated_delivery: Optional[str]
    customer_notes: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]


class OrderSummaryResponse(BaseModel):
    id: str
    order_number: str
    status: str
    status_label: str
    total: int
    currency: str
    item_count: int
    created_at: str


# Products
class ProductResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    short_description: Optional[str] = None
    product_type: str
    category: Optional[str]
    execution_type: Optional[str] = None  # pontual / recorrente
    sectors: List[str]
    sku: Optional[str]
    price: int
    price_usd: Optional[int] = 0
    price_eur: Optional[int] = 0
    currency: str
    unit_label: Optional[str]
    is_active: bool
    requires_site: bool
    requires_scheduling: Optional[bool] = False
    min_area_ha: Optional[int] = None
    duration_hours: Optional[int] = None
    deliverables: Optional[List[str]] = None
    image_url: Optional[str]
    is_featured: Optional[bool] = False


class SectorMismatchWarning(BaseModel):
    warning: bool
    sector_mismatch: bool
    product_sector: str
    product_sector_label: str
    account_sector: str
    account_sector_label: str
    message: str
    suggestion: str


class SectorLabel(BaseModel):
    key: str
    label: str


# ============ STATUS LABELS ============

STATUS_LABELS = {
    "created": "Criado",
    "awaiting_payment": "Aguardando Pagamento",
    "paid": "Pago",
    "processing": "Em Processamento",
    "dispatched": "Enviado",
    "assigned": "Equipa Atribuída",
    "in_progress": "Em Andamento",
    "delivered": "Entregue",
    "completed": "Concluído",
    "refunded": "Reembolsado",
    "cancelled": "Cancelado",
    "partially_refunded": "Parcialmente Reembolsado",
}


# ============ PRODUCT ENDPOINTS ============

@router.get("/products", response_model=List[ProductResponse])
async def list_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    sector: Optional[str] = Query(None, description="Filter by sector (e.g., agriculture, mining)"),
    product_type: Optional[str] = Query(None, description="Filter by type (physical, digital, service, subscription)"),
    search: Optional[str] = Query(None, description="Search by name"),
    db: Session = Depends(get_db),
):
    """
    List available products with optional filtering.
    """
    cart_service = get_cart_service(db)
    products = cart_service.list_products()
    
    # Apply filters
    if category:
        products = [p for p in products if p.get("category") == category]
    
    if sector:
        products = [p for p in products if sector in p.get("sectors", [])]
    
    if product_type:
        products = [p for p in products if p.get("product_type") == product_type]
    
    if search:
        search_lower = search.lower()
        products = [p for p in products if search_lower in p.get("name", "").lower()]
    
    return [
        ProductResponse(
            id=p["id"],
            name=p["name"],
            description=p.get("description"),
            short_description=p.get("short_description"),
            product_type=p.get("product_type", "service"),
            category=p.get("category"),
            execution_type=p.get("execution_type"),
            sectors=p.get("sectors", []),
            sku=p.get("sku"),
            price=p["price"],
            price_usd=p.get("price_usd", 0),
            price_eur=p.get("price_eur", 0),
            currency=p.get("currency", "AOA"),
            unit_label=p.get("unit_label"),
            is_active=p.get("is_active", True),
            requires_site=p.get("requires_site", False),
            requires_scheduling=p.get("requires_scheduling", False),
            min_area_ha=p.get("min_area_ha"),
            duration_hours=p.get("duration_hours"),
            deliverables=p.get("deliverables"),
            image_url=p.get("image_url"),
            is_featured=p.get("is_featured", False),
        )
        for p in products
    ]


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, db: Session = Depends(get_db)):
    """Get product details."""
    cart_service = get_cart_service(db)
    product = cart_service.get_product(product_id)
    
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    return ProductResponse(
        id=product["id"],
        name=product["name"],
        description=product.get("description"),
        short_description=product.get("short_description"),
        product_type=product.get("product_type", "service"),
        category=product.get("category"),
        execution_type=product.get("execution_type"),
        sectors=product.get("sectors", []),
        sku=product.get("sku"),
        price=product["price"],
        price_usd=product.get("price_usd", 0),
        price_eur=product.get("price_eur", 0),
        currency=product.get("currency", "AOA"),
        unit_label=product.get("unit_label"),
        is_active=product.get("is_active", True),
        requires_site=product.get("requires_site", False),
        requires_scheduling=product.get("requires_scheduling", False),
        min_area_ha=product.get("min_area_ha"),
        duration_hours=product.get("duration_hours"),
        deliverables=product.get("deliverables"),
        image_url=product.get("image_url"),
        is_featured=product.get("is_featured", False),
    )


# ============ SECTOR ENDPOINTS ============

@router.get("/sectors", response_model=List[SectorLabel])
async def list_sectors():
    """List available sectors with labels."""
    sector_labels = get_sector_labels()
    return [
        SectorLabel(key=k, label=v)
        for k, v in sector_labels.items()
    ]


@router.post("/check-sector-mismatch")
async def check_sector_mismatch(
    product_id: str = Body(..., embed=True),
    account_sector: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db),
):
    """
    Check if a product sector matches the account sector.
    Returns warning info if mismatch - does NOT block purchase.
    """
    cart_service = get_cart_service(db)
    warning = cart_service.check_sector_mismatch(product_id, account_sector)
    
    if warning:
        return warning
    
    return {"warning": False, "sector_mismatch": False}


@router.get("/cart/{cart_id}/with-warnings")
async def get_cart_with_warnings(
    cart_id: str,
    account_sector: Optional[str] = Query(None, description="Account sector for mismatch checking"),
    db: Session = Depends(get_db),
):
    """
    Get cart with sector mismatch warnings for each item.
    Warnings are informational only - purchase is not blocked.
    """
    cart_service = get_cart_service(db)
    try:
        return cart_service.get_cart_with_warnings(cart_id, account_sector)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ CART ENDPOINTS ============

@router.get("/cart/{cart_id}", response_model=CartResponse)
async def get_cart(cart_id: str, db: Session = Depends(get_db)):
    """Get cart contents."""
    cart_service = get_cart_service(db)
    cart = cart_service.get_or_create_cart(session_id=cart_id)
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.post("/cart/{cart_id}/items", response_model=CartResponse)
async def add_to_cart(cart_id: str, request: AddToCartRequest, db: Session = Depends(get_db)):
    """Add item to cart."""
    cart_service = get_cart_service(db)
    
    scheduled = None
    if request.scheduled_date:
        scheduled = datetime.fromisoformat(request.scheduled_date.replace("Z", "+00:00"))
    
    # Ensure cart exists
    cart_service.get_or_create_cart(session_id=cart_id)
    
    try:
        cart = cart_service.add_item(
            cart_id=cart_id,
            product_id=request.product_id,
            quantity=request.quantity,
            scheduled_date=scheduled,
            custom_options=request.custom_options,
            currency=request.currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.put("/cart/{cart_id}/items/{item_id}", response_model=CartResponse)
async def update_cart_item(cart_id: str, item_id: str, request: UpdateCartItemRequest, db: Session = Depends(get_db)):
    """Update cart item quantity."""
    cart_service = get_cart_service(db)
    cart = cart_service.update_item_quantity(cart_id, item_id, request.quantity)
    
    if not cart:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.delete("/cart/{cart_id}/items/{item_id}", response_model=CartResponse)
async def remove_cart_item(cart_id: str, item_id: str, db: Session = Depends(get_db)):
    """Remove item from cart."""
    cart_service = get_cart_service(db)
    cart = cart_service.remove_item(cart_id, item_id)
    
    if not cart:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.patch("/cart/{cart_id}/currency", response_model=CartResponse)
async def update_cart_currency(cart_id: str, request: UpdateCurrencyRequest, db: Session = Depends(get_db)):
    """Update cart currency and recalculate all item prices."""
    cart_service = get_cart_service(db)
    try:
        cart = cart_service.update_currency(cart_id, request.currency)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.post("/cart/{cart_id}/coupon", response_model=CartResponse)
async def apply_coupon(cart_id: str, request: ApplyCouponRequest, db: Session = Depends(get_db)):
    """Apply coupon to cart."""
    cart_service = get_cart_service(db)
    result = cart_service.apply_coupon(cart_id, request.code)
    
    if not result.valid:
        raise HTTPException(status_code=400, detail=result.message)
    
    cart = cart_service.get_cart(cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Carrinho não encontrado")
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.delete("/cart/{cart_id}/coupon", response_model=CartResponse)
async def remove_coupon(cart_id: str, db: Session = Depends(get_db)):
    """Remove coupon from cart."""
    cart_service = get_cart_service(db)
    cart = cart_service.remove_coupon(cart_id)
    
    if not cart:
        raise HTTPException(status_code=404, detail="Carrinho não encontrado")
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.post("/cart/{cart_id}/delivery", response_model=CartResponse)
async def set_delivery(cart_id: str, request: SetDeliveryRequest, db: Session = Depends(get_db)):
    """Set delivery method for cart."""
    cart_service = get_cart_service(db)
    cart = cart_service.set_delivery(cart_id, request.delivery_method)
    
    if not cart:
        raise HTTPException(status_code=404, detail="Carrinho não encontrado")
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.post("/cart/{cart_id}/site", response_model=CartResponse)
async def set_cart_site(cart_id: str, request: SetSiteRequest, db: Session = Depends(get_db)):
    """Set site for service products."""
    cart_service = get_cart_service(db)
    cart = cart_service.set_site(cart_id, request.site_id)
    
    if not cart:
        raise HTTPException(status_code=404, detail="Carrinho não encontrado")
    
    return CartResponse(
        id=cart.id,
        user_id=cart.user_id,
        company_id=cart.company_id,
        site_id=cart.site_id,
        items=[
            CartItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                tax_rate=item.tax_rate,
                tax_amount=item.tax_amount,
                scheduled_date=item.scheduled_date.isoformat() if item.scheduled_date else None,
                custom_options=item.custom_options,
            )
            for item in cart.items
        ],
        subtotal=cart.subtotal,
        discount_amount=cart.discount_amount,
        coupon_code=cart.coupon_code,
        tax_rate=cart.tax_rate,
        tax_amount=cart.tax_amount,
        delivery_cost=cart.delivery_cost,
        delivery_method=cart.delivery_method,
        total=cart.total,
        currency=cart.currency,
        item_count=cart.item_count,
    )


@router.delete("/cart/{cart_id}")
async def clear_cart(cart_id: str, db: Session = Depends(get_db)):
    """Clear cart contents."""
    cart_service = get_cart_service(db)
    cart_service.clear_cart(cart_id)
    return {"message": "Carrinho limpo com sucesso"}


# ============ CHECKOUT ENDPOINTS ============

@router.get("/payment-methods")
def get_payment_methods():
    """Return available payment methods per currency."""
    from app.services.orders import CURRENCY_PAYMENT_METHODS
    return {
        currency: [{"value": m.value, "label": m.value} for m in methods]
        for currency, methods in CURRENCY_PAYMENT_METHODS.items()
    }


@router.get("/stripe-config")
def get_stripe_config():
    """Return Stripe publishable key for frontend initialization."""
    import os
    pk = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    return {
        "publishable_key": pk,
        "enabled": bool(pk),
    }


@router.post("/checkout/{cart_id}", response_model=CheckoutResponse)
async def checkout(cart_id: str, request: CheckoutRequest, user: Optional[User] = Depends(get_optional_user), db: Session = Depends(get_db)):
    """
    Process checkout and create order.
    
    Supports both authenticated users and guest checkout.
    
    Payment methods:
    - multicaixa_express: Returns QR code for Multicaixa app
    - visa_mastercard: Returns Stripe Payment Element
    - iban_angola: Returns Angolan bank transfer details
    - iban_international: Returns international wire transfer details
    """
    
    # Validate payment method
    try:
        payment_method = PaymentMethod(request.payment_method)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Método de pagamento inválido: {request.payment_method}"
        )

    # Validate currency
    req_currency = (request.currency or "AOA").upper()
    if req_currency not in ("AOA", "USD", "EUR"):
        raise HTTPException(status_code=400, detail=f"Moeda inválida: {req_currency}")

    # Validate currency ↔ payment method compatibility
    from app.services.orders import CURRENCY_PAYMENT_METHODS
    allowed = CURRENCY_PAYMENT_METHODS.get(req_currency, [])
    if payment_method not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Método {payment_method.value} não disponível para {req_currency}. "
                   f"Opções: {', '.join(m.value for m in allowed)}"
        )

    order_service = get_order_service(db)
    
    result = await order_service.checkout(
        cart_id=cart_id,
        user_id=user.id if user else None,
        payment_method=payment_method,
        billing_info=request.billing_info.model_dump(),
        customer_notes=request.customer_notes,
        currency=req_currency,
    )
    
    return CheckoutResponse(
        success=result.success,
        order_id=result.order_id,
        order_number=result.order_number,
        payment_required=result.payment_required,
        payment_method=result.payment_method,
        payment_data=result.payment_data,
        error=result.error,
    )


# ============ ORDER ENDPOINTS ============

@router.get("/orders", response_model=List[OrderSummaryResponse])
async def list_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List orders for the authenticated user."""
    
    order_service = get_order_service(db)
    orders = order_service.list_orders(
        user_id=user.id,
        status=status,
        limit=limit,
    )
    
    return [
        OrderSummaryResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            status_label=STATUS_LABELS.get(order.status, order.status),
            total=order.total,
            currency=order.currency,
            item_count=len(order.items),
            created_at=order.created_at.isoformat(),
        )
        for order in orders
    ]


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    """Get full order details with timeline."""
    
    order_service = get_order_service(db)
    order = order_service.get_order(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    return OrderResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        status_label=STATUS_LABELS.get(order.status, order.status),
        payment_method=order.payment_method,
        payment_reference=order.payment_reference,
        currency=order.currency,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        coupon_code=order.coupon_code,
        tax_amount=order.tax_amount,
        delivery_cost=order.delivery_cost,
        total=order.total,
        items=[
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                status=item.status,
            )
            for item in order.items
        ],
        events=[
            OrderEventResponse(
                id=event.id,
                event_type=event.event_type,
                title=event.title,
                description=event.description,
                actor_name=event.actor_name,
                is_customer_visible=event.is_customer_visible,
                created_at=event.created_at.isoformat(),
            )
            for event in order.events
            if event.is_customer_visible
        ],
        deliverables=[
            DeliverableResponse(
                id=d.id,
                name=d.name,
                description=d.description,
                deliverable_type=d.deliverable_type,
                file_size=d.file_size,
                mime_type=d.mime_type,
                download_url=d.download_url,
                is_ready=d.is_ready,
                created_at=d.created_at.isoformat(),
            )
            for d in order.deliverables
        ],
        delivery_method=order.delivery_method,
        assigned_team=order.assigned_team,
        scheduled_start=order.scheduled_start.isoformat() if order.scheduled_start else None,
        estimated_delivery=order.estimated_delivery.isoformat() if order.estimated_delivery else None,
        customer_notes=order.customer_notes,
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        completed_at=order.completed_at.isoformat() if order.completed_at else None,
    )


@router.get("/orders/number/{order_number}", response_model=OrderResponse)
async def get_order_by_number(order_number: str, db: Session = Depends(get_db)):
    """Get order by order number (e.g., GV-2025-000001)."""
    
    order_service = get_order_service(db)
    order = order_service.get_order_by_number(order_number)
    
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    return OrderResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        status_label=STATUS_LABELS.get(order.status, order.status),
        payment_method=order.payment_method,
        payment_reference=order.payment_reference,
        currency=order.currency,
        subtotal=order.subtotal,
        discount_amount=order.discount_amount,
        coupon_code=order.coupon_code,
        tax_amount=order.tax_amount,
        delivery_cost=order.delivery_cost,
        total=order.total,
        items=[
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                product_type=item.product_type,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                status=item.status,
            )
            for item in order.items
        ],
        events=[
            OrderEventResponse(
                id=event.id,
                event_type=event.event_type,
                title=event.title,
                description=event.description,
                actor_name=event.actor_name,
                is_customer_visible=event.is_customer_visible,
                created_at=event.created_at.isoformat(),
            )
            for event in order.events
            if event.is_customer_visible
        ],
        deliverables=[
            DeliverableResponse(
                id=d.id,
                name=d.name,
                description=d.description,
                deliverable_type=d.deliverable_type,
                file_size=d.file_size,
                mime_type=d.mime_type,
                download_url=d.download_url,
                is_ready=d.is_ready,
                created_at=d.created_at.isoformat(),
            )
            for d in order.deliverables
        ],
        delivery_method=order.delivery_method,
        assigned_team=order.assigned_team,
        scheduled_start=order.scheduled_start.isoformat() if order.scheduled_start else None,
        estimated_delivery=order.estimated_delivery.isoformat() if order.estimated_delivery else None,
        customer_notes=order.customer_notes,
        created_at=order.created_at.isoformat(),
        updated_at=order.updated_at.isoformat(),
        completed_at=order.completed_at.isoformat() if order.completed_at else None,
    )


class CancelOrderRequest(BaseModel):
    reason: Optional[str] = None

@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, request: CancelOrderRequest = Body(default=CancelOrderRequest()), db: Session = Depends(get_db)):
    """Cancel an order."""
    
    order_service = get_order_service(db)
    success = await order_service.cancel_order(
        order_id=order_id,
        reason=request.reason,
        cancelled_by="Cliente",
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível cancelar o pedido")
    
    return {"message": "Pedido cancelado com sucesso"}


# ============ MY ACCOUNT ENDPOINTS (Minhas Compras) ============

@router.get("/me/orders", response_model=List[OrderSummaryResponse])
async def my_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get customer's orders (Minhas Compras)."""
    
    order_service = get_order_service(db)
    orders = order_service.list_orders(
        user_id=str(user.id),
        status=status,
    )
    
    return [
        OrderSummaryResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            status_label=STATUS_LABELS.get(order.status, order.status),
            total=order.total,
            currency=order.currency,
            item_count=len(order.items),
            created_at=order.created_at.isoformat(),
        )
        for order in orders
    ]


@router.get("/me/deliverables", response_model=List[DeliverableResponse])
async def my_deliverables(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Get all deliverables from customer's orders."""
    
    order_service = get_order_service(db)
    orders = order_service.list_orders(user_id=str(user.id))
    
    deliverables = []
    for order in orders:
        for d in order.deliverables:
            if d.is_ready:
                deliverables.append(
                    DeliverableResponse(
                        id=d.id,
                        name=d.name,
                        description=d.description,
                        deliverable_type=d.deliverable_type,
                        file_size=d.file_size,
                        mime_type=d.mime_type,
                        download_url=d.download_url,
                        is_ready=d.is_ready,
                        created_at=d.created_at.isoformat(),
                    )
                )
    
    return deliverables


# ============ ADMIN ENDPOINTS ============

class ConfirmPaymentRequest(BaseModel):
    payment_reference: Optional[str] = None

@router.post("/admin/orders/{order_id}/confirm-payment")
async def admin_confirm_payment(
    order_id: str,
    request: ConfirmPaymentRequest = Body(default=ConfirmPaymentRequest()),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin: Confirm payment (for IBAN transfers).
    """
    
    order_service = get_order_service(db)
    success = await order_service.confirm_payment(
        order_id=order_id,
        payment_reference=request.payment_reference,
        confirmed_by="Admin",
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível confirmar o pagamento")
    
    return {"message": "Pagamento confirmado com sucesso"}


@router.post("/admin/orders/{order_id}/assign-team")
async def admin_assign_team(
    order_id: str,
    team_name: str = Body(..., embed=True),
    scheduled_start: Optional[str] = Body(None, embed=True),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin: Assign team for service execution.
    """
    
    scheduled = None
    if scheduled_start:
        scheduled = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
    
    order_service = get_order_service(db)
    success = await order_service.assign_team(
        order_id=order_id,
        team_name=team_name,
        scheduled_start=scheduled,
        assigned_by="Admin",
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível atribuir a equipa")
    
    return {"message": f"Equipa {team_name} atribuída com sucesso"}


@router.post("/admin/orders/{order_id}/start-service")
async def admin_start_service(order_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Admin: Mark service as started (check-in).
    """
    
    order_service = get_order_service(db)
    success = await order_service.start_service(order_id, started_by="Equipa")
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível iniciar o serviço")
    
    return {"message": "Serviço iniciado com sucesso"}


class CompleteServiceRequest(BaseModel):
    notes: Optional[str] = None

@router.post("/admin/orders/{order_id}/complete-service")
async def admin_complete_service(
    order_id: str,
    request: CompleteServiceRequest = Body(default=CompleteServiceRequest()),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin: Mark service as completed (check-out).
    """
    
    order_service = get_order_service(db)
    success = await order_service.complete_service(
        order_id=order_id,
        completed_by="Equipa",
        notes=request.notes,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível completar o serviço")
    
    return {"message": "Serviço concluído com sucesso"}


class ShipOrderRequest(BaseModel):
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None

@router.post("/admin/orders/{order_id}/ship")
async def admin_ship_order(
    order_id: str,
    request: ShipOrderRequest = Body(default=ShipOrderRequest()),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin: Mark physical order as shipped.
    """
    
    order_service = get_order_service(db)
    success = await order_service.ship_order(
        order_id=order_id,
        tracking_number=request.tracking_number,
        carrier=request.carrier,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível marcar como enviado")
    
    return {"message": "Pedido marcado como enviado"}


@router.post("/admin/orders/{order_id}/deliver")
async def admin_deliver_order(order_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """
    Admin: Mark order as delivered.
    """
    
    order_service = get_order_service(db)
    success = await order_service.deliver_order(order_id, delivered_by="Transportadora")
    
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível marcar como entregue")
    
    return {"message": "Pedido marcado como entregue"}


class AddDeliverableRequest(BaseModel):
    name: str
    deliverable_type: str
    download_url: Optional[str] = None
    description: Optional[str] = None

@router.post("/admin/orders/{order_id}/deliverables")
async def admin_add_deliverable(
    order_id: str,
    request: AddDeliverableRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Admin: Add deliverable file to order.
    """
    
    order_service = get_order_service(db)
    deliverable_id = await order_service.add_deliverable(
        order_id=order_id,
        name=request.name,
        deliverable_type=request.deliverable_type,
        download_url=request.download_url,
        description=request.description,
    )
    
    if not deliverable_id:
        raise HTTPException(status_code=400, detail="Não foi possível adicionar o ficheiro")
    
    return {"message": "Ficheiro adicionado com sucesso", "deliverable_id": deliverable_id}
