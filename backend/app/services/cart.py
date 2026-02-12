"""
Cart Service

Manages shopping cart operations:
- Add/remove items
- Update quantities
- Apply coupons
- Calculate totals with tax and delivery
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============ DATA CLASSES ============

@dataclass
class CartItemData:
    """Cart item representation."""
    id: str
    product_id: str
    variant_id: Optional[str]
    product_name: str
    product_type: str
    product_image: Optional[str]
    sku: Optional[str]
    quantity: int
    unit_price: int  # In smallest currency unit
    total_price: int
    tax_rate: float
    tax_amount: int
    scheduled_date: Optional[datetime] = None
    custom_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CartData:
    """Cart representation."""
    id: str
    user_id: Optional[str]
    company_id: Optional[str]
    session_id: Optional[str]
    site_id: Optional[str]
    items: List[CartItemData]
    item_count: int
    subtotal: int
    discount_amount: int
    discount_type: Optional[str]
    coupon_code: Optional[str]
    tax_rate: float
    tax_amount: int
    delivery_cost: int
    delivery_method: Optional[str]
    total: int
    currency: str
    created_at: datetime
    updated_at: datetime


@dataclass
class CouponValidation:
    """Coupon validation result."""
    valid: bool
    code: str
    discount_type: Optional[str] = None
    discount_value: Optional[int] = None
    discount_amount: int = 0
    error: Optional[str] = None


# ============ TAX CONFIGURATION ============

TAX_RATES = {
    "AO": 0.14,  # Angola IVA 14%
    "PT": 0.23,  # Portugal IVA 23%
    "US": 0.0,   # No federal sales tax
    "default": 0.14,
}


# ============ IN-MEMORY STORES ============

_carts_store: Dict[str, dict] = {}
_products_store: Dict[str, dict] = {}  # Product cache
_coupons_store: Dict[str, dict] = {}


# ============ SEED DEMO PRODUCTS ============

def seed_demo_products():
    """Seed demo products for the shop."""
    products = [
        {
            "id": "prod_ndvi_basic",
            "name": "Análise NDVI Básica",
            "slug": "ndvi-basico",
            "description": "Análise de saúde vegetal com índice NDVI para áreas até 50 hectares.",
            "short_description": "NDVI até 50ha",
            "product_type": "service",
            "category": "analysis",
            "price": 15000000,  # 150.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 24,
            "requires_site": True,
            "sectors": ["agro"],
            "image_url": "/assets/img/products/ndvi.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_ndvi_premium",
            "name": "Análise NDVI Premium",
            "slug": "ndvi-premium",
            "description": "Análise completa de saúde vegetal com relatório detalhado e recomendações.",
            "short_description": "NDVI completo + relatório",
            "product_type": "service",
            "category": "analysis",
            "price": 35000000,  # 350.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "sectors": ["agro"],
            "image_url": "/assets/img/products/ndvi-premium.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_mapping_3d",
            "name": "Mapeamento 3D",
            "slug": "mapeamento-3d",
            "description": "Modelo 3D de alta resolução com ortomosaico e nuvem de pontos.",
            "short_description": "Modelo 3D + Ortomosaico",
            "product_type": "service",
            "category": "mapping",
            "price": 75000000,  # 750.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "sectors": ["construction", "mining", "infrastructure"],
            "image_url": "/assets/img/products/mapping-3d.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_spraying",
            "name": "Pulverização por Drone",
            "slug": "pulverizacao-drone",
            "description": "Serviço de pulverização agrícola com drone DJI Agras. Inclui produto fitossanitário.",
            "short_description": "Pulverização até 100ha/dia",
            "product_type": "service",
            "category": "spraying",
            "price": 5000000,  # 50.000 AOA por hectare
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 8,
            "requires_site": True,
            "requires_scheduling": True,
            "sectors": ["agro"],
            "image_url": "/assets/img/products/spraying.jpg",
            "is_active": True,
        },
        {
            "id": "prod_monitoring_monthly",
            "name": "Monitorização Mensal",
            "slug": "monitorizacao-mensal",
            "description": "Subscrição mensal com 2 voos, relatórios NDVI e alertas automáticos.",
            "short_description": "2 voos/mês + alertas",
            "product_type": "subscription",
            "category": "monitoring",
            "price": 25000000,  # 250.000 AOA/mês
            "currency": "AOA",
            "tax_rate": 0.14,
            "requires_site": True,
            "sectors": ["agro", "mining"],
            "image_url": "/assets/img/products/monitoring.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_sensor_soil",
            "name": "Sensor de Solo IoT",
            "slug": "sensor-solo-iot",
            "description": "Sensor de humidade, temperatura e pH do solo com conectividade LoRa.",
            "short_description": "Sensor solo + 1 ano dados",
            "product_type": "physical",
            "category": "hardware",
            "price": 12000000,  # 120.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "track_inventory": True,
            "stock_quantity": 50,
            "sectors": ["agro"],
            "image_url": "/assets/img/products/sensor-soil.jpg",
            "is_active": True,
        },
        {
            "id": "prod_seeds_maize",
            "name": "Sementes de Milho Certificadas",
            "slug": "sementes-milho",
            "description": "Sementes de milho híbrido de alta produtividade. Saco de 25kg.",
            "short_description": "Saco 25kg",
            "product_type": "physical",
            "category": "supplies",
            "price": 4500000,  # 45.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "track_inventory": True,
            "stock_quantity": 200,
            "sectors": ["agro"],
            "image_url": "/assets/img/products/seeds.jpg",
            "is_active": True,
        },
        {
            "id": "prod_feed_cattle",
            "name": "Ração Bovino Premium",
            "slug": "racao-bovino",
            "description": "Ração balanceada para gado bovino. Saco de 50kg.",
            "short_description": "Saco 50kg",
            "product_type": "physical",
            "category": "supplies",
            "price": 7500000,  # 75.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "track_inventory": True,
            "stock_quantity": 150,
            "sectors": ["livestock"],
            "image_url": "/assets/img/products/feed.jpg",
            "is_active": True,
        },
    ]
    
    for p in products:
        p["created_at"] = datetime.utcnow()
        p["updated_at"] = datetime.utcnow()
        _products_store[p["id"]] = p
    
    # Demo coupons
    _coupons_store["WELCOME10"] = {
        "code": "WELCOME10",
        "discount_type": "percentage",
        "discount_value": 10,
        "minimum_order": 5000000,
        "usage_limit": 100,
        "usage_count": 0,
        "is_active": True,
        "first_order_only": True,
    }
    _coupons_store["DRONE50K"] = {
        "code": "DRONE50K",
        "discount_type": "fixed",
        "discount_value": 5000000,  # 50.000 AOA off
        "minimum_order": 50000000,
        "usage_limit": 50,
        "usage_count": 0,
        "is_active": True,
    }
    
    return len(products)


# Seed on import
seed_demo_products()


# ============ CART SERVICE ============

class CartService:
    """Shopping cart service."""
    
    def get_or_create_cart(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        company_id: Optional[str] = None,
    ) -> CartData:
        """Get existing cart or create new one."""
        
        # Find existing cart
        cart = None
        if user_id:
            cart = next(
                (c for c in _carts_store.values() 
                 if c.get("user_id") == user_id and c.get("is_active")),
                None
            )
        elif session_id:
            cart = next(
                (c for c in _carts_store.values() 
                 if c.get("session_id") == session_id and c.get("is_active")),
                None
            )
        
        if cart:
            return self._cart_to_data(cart)
        
        # Create new cart
        cart_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        cart = {
            "id": cart_id,
            "user_id": user_id,
            "company_id": company_id,
            "session_id": session_id or str(uuid.uuid4()),
            "site_id": None,
            "items": [],
            "coupon_code": None,
            "discount_amount": 0,
            "discount_type": None,
            "delivery_method": None,
            "delivery_cost": 0,
            "delivery_address": None,
            "subtotal": 0,
            "tax_amount": 0,
            "total": 0,
            "currency": "AOA",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            "expires_at": now + timedelta(days=7),
        }
        
        _carts_store[cart_id] = cart
        
        return self._cart_to_data(cart)
    
    def _find_cart(self, cart_id: str) -> Optional[dict]:
        """Find cart by ID or session_id."""
        cart = _carts_store.get(cart_id)
        if cart and cart.get("is_active"):
            return cart
        # Try by session_id
        return self._get_cart_dict_by_session(cart_id)
    
    def get_cart(self, cart_id: str) -> Optional[CartData]:
        """Get cart by ID or session_id."""
        cart = self._find_cart(cart_id)
        if cart:
            return self._cart_to_data(cart)
        return None
    
    def get_cart_by_session(self, session_id: str) -> Optional[CartData]:
        """Get cart by session ID."""
        cart = next(
            (c for c in _carts_store.values() 
             if c.get("session_id") == session_id and c.get("is_active")),
            None
        )
        if cart:
            return self._cart_to_data(cart)
        return None
    
    def _get_cart_dict_by_session(self, session_id: str) -> Optional[dict]:
        """Get raw cart dict by session ID (internal use)."""
        return next(
            (c for c in _carts_store.values() 
             if c.get("session_id") == session_id and c.get("is_active")),
            None
        )
    
    def add_item(
        self,
        cart_id: str,
        product_id: str,
        quantity: int = 1,
        variant_id: Optional[str] = None,
        scheduled_date: Optional[datetime] = None,
        custom_options: Optional[Dict[str, Any]] = None,
    ) -> CartData:
        """Add item to cart."""
        
        # Try to find cart by ID or session_id
        cart = _carts_store.get(cart_id) or self._get_cart_dict_by_session(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        
        product = _products_store.get(product_id)
        if not product:
            raise ValueError("Product not found")
        
        if not product.get("is_active"):
            raise ValueError("Product is not available")
        
        # Check stock for physical products
        if product.get("track_inventory"):
            if product.get("stock_quantity", 0) < quantity:
                raise ValueError("Insufficient stock")
        
        # Check if item already in cart
        existing_item = next(
            (i for i in cart["items"] 
             if i["product_id"] == product_id and i.get("variant_id") == variant_id),
            None
        )
        
        price = product["price"]
        tax_rate = product.get("tax_rate", 0.14)
        
        if existing_item:
            existing_item["quantity"] += quantity
            existing_item["total_price"] = existing_item["unit_price"] * existing_item["quantity"]
            existing_item["tax_amount"] = int(existing_item["total_price"] * tax_rate)
        else:
            item = {
                "id": str(uuid.uuid4()),
                "product_id": product_id,
                "variant_id": variant_id,
                "product_name": product["name"],
                "product_type": product["product_type"],
                "product_image": product.get("image_url"),
                "sku": product.get("sku"),
                "quantity": quantity,
                "unit_price": price,
                "total_price": price * quantity,
                "tax_rate": tax_rate,
                "tax_amount": int(price * quantity * tax_rate),
                "scheduled_date": scheduled_date,
                "custom_options": custom_options or {},
            }
            cart["items"].append(item)
        
        self._recalculate_cart(cart)
        
        return self._cart_to_data(cart)
    
    def update_item_quantity(
        self,
        cart_id: str,
        item_id: str,
        quantity: int,
    ) -> CartData:
        """Update item quantity."""
        
        cart = self._find_cart(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        
        item = next((i for i in cart["items"] if i["id"] == item_id), None)
        if not item:
            raise ValueError("Item not found in cart")
        
        if quantity <= 0:
            cart["items"] = [i for i in cart["items"] if i["id"] != item_id]
        else:
            # Check stock
            product = _products_store.get(item["product_id"])
            if product and product.get("track_inventory"):
                if product.get("stock_quantity", 0) < quantity:
                    raise ValueError("Insufficient stock")
            
            item["quantity"] = quantity
            item["total_price"] = item["unit_price"] * quantity
            item["tax_amount"] = int(item["total_price"] * item["tax_rate"])
        
        self._recalculate_cart(cart)
        
        return self._cart_to_data(cart)
    
    def remove_item(self, cart_id: str, item_id: str) -> CartData:
        """Remove item from cart."""
        return self.update_item_quantity(cart_id, item_id, 0)
    
    def apply_coupon(self, cart_id: str, coupon_code: str) -> CouponValidation:
        """Apply coupon to cart."""
        
        cart = self._find_cart(cart_id)
        if not cart:
            return CouponValidation(valid=False, code=coupon_code, error="Cart not found")
        
        code_upper = coupon_code.upper().strip()
        coupon = _coupons_store.get(code_upper)
        
        if not coupon:
            return CouponValidation(valid=False, code=coupon_code, error="Cupão inválido")
        
        if not coupon.get("is_active"):
            return CouponValidation(valid=False, code=coupon_code, error="Cupão expirado")
        
        if coupon.get("usage_limit") and coupon.get("usage_count", 0) >= coupon["usage_limit"]:
            return CouponValidation(valid=False, code=coupon_code, error="Cupão esgotado")
        
        subtotal = cart.get("subtotal", 0)
        if coupon.get("minimum_order") and subtotal < coupon["minimum_order"]:
            min_order = coupon["minimum_order"] / 100
            return CouponValidation(
                valid=False, 
                code=coupon_code, 
                error=f"Pedido mínimo de {min_order:,.0f} AOA"
            )
        
        # Calculate discount
        discount_type = coupon["discount_type"]
        discount_value = coupon["discount_value"]
        
        if discount_type == "percentage":
            discount_amount = int(subtotal * discount_value / 100)
            if coupon.get("maximum_discount"):
                discount_amount = min(discount_amount, coupon["maximum_discount"])
        else:
            discount_amount = discount_value
        
        # Apply to cart
        cart["coupon_code"] = code_upper
        cart["discount_type"] = discount_type
        cart["discount_amount"] = discount_amount
        
        self._recalculate_cart(cart)
        
        return CouponValidation(
            valid=True,
            code=code_upper,
            discount_type=discount_type,
            discount_value=discount_value,
            discount_amount=discount_amount,
        )
    
    def remove_coupon(self, cart_id: str) -> CartData:
        """Remove coupon from cart."""
        
        cart = self._find_cart(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        
        cart["coupon_code"] = None
        cart["discount_type"] = None
        cart["discount_amount"] = 0
        
        self._recalculate_cart(cart)
        
        return self._cart_to_data(cart)
    
    def set_delivery(
        self,
        cart_id: str,
        delivery_method: str,
        delivery_address: Optional[Dict[str, Any]] = None,
    ) -> CartData:
        """Set delivery method and address."""
        
        cart = self._find_cart(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        
        # Calculate delivery cost based on method
        delivery_costs = {
            "pickup": 0,
            "luanda": 500000,      # 5.000 AOA
            "provinces": 1500000,   # 15.000 AOA
            "international": 5000000,  # 50.000 AOA
        }
        
        cart["delivery_method"] = delivery_method
        cart["delivery_cost"] = delivery_costs.get(delivery_method, 0)
        cart["delivery_address"] = delivery_address
        
        self._recalculate_cart(cart)
        
        return self._cart_to_data(cart)
    
    def set_site(self, cart_id: str, site_id: str) -> CartData:
        """Associate cart with a site (for services)."""
        
        cart = self._find_cart(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        
        cart["site_id"] = site_id
        cart["updated_at"] = datetime.utcnow()
        
        return self._cart_to_data(cart)
    
    def clear_cart(self, cart_id: str) -> bool:
        """Clear all items from cart."""
        
        cart = self._find_cart(cart_id)
        if not cart:
            return False
        
        cart["items"] = []
        cart["coupon_code"] = None
        cart["discount_amount"] = 0
        cart["discount_type"] = None
        
        self._recalculate_cart(cart)
        
        return True
    
    def _recalculate_cart(self, cart: dict) -> None:
        """Recalculate cart totals."""
        
        subtotal = sum(item["total_price"] for item in cart["items"])
        tax_amount = sum(item["tax_amount"] for item in cart["items"])
        
        discount = cart.get("discount_amount", 0)
        delivery = cart.get("delivery_cost", 0)
        
        total = subtotal - discount + delivery
        
        cart["subtotal"] = subtotal
        cart["tax_amount"] = tax_amount
        cart["total"] = max(0, total)
        cart["updated_at"] = datetime.utcnow()
    
    def _cart_to_data(self, cart: dict) -> CartData:
        """Convert cart dict to CartData."""
        
        items = [
            CartItemData(
                id=i["id"],
                product_id=i["product_id"],
                variant_id=i.get("variant_id"),
                product_name=i["product_name"],
                product_type=i["product_type"],
                product_image=i.get("product_image"),
                sku=i.get("sku"),
                quantity=i["quantity"],
                unit_price=i["unit_price"],
                total_price=i["total_price"],
                tax_rate=i.get("tax_rate", 0),
                tax_amount=i.get("tax_amount", 0),
                scheduled_date=i.get("scheduled_date"),
                custom_options=i.get("custom_options", {}),
            )
            for i in cart.get("items", [])
        ]
        
        return CartData(
            id=cart["id"],
            user_id=cart.get("user_id"),
            company_id=cart.get("company_id"),
            session_id=cart.get("session_id"),
            site_id=cart.get("site_id"),
            items=items,
            item_count=len(items),
            subtotal=cart.get("subtotal", 0),
            discount_amount=cart.get("discount_amount", 0),
            discount_type=cart.get("discount_type"),
            coupon_code=cart.get("coupon_code"),
            tax_rate=cart.get("tax_rate", 0.14),
            tax_amount=cart.get("tax_amount", 0),
            delivery_cost=cart.get("delivery_cost", 0),
            delivery_method=cart.get("delivery_method"),
            total=cart.get("total", 0),
            currency=cart.get("currency", "AOA"),
            created_at=cart.get("created_at", datetime.utcnow()),
            updated_at=cart.get("updated_at", datetime.utcnow()),
        )
    
    def list_products(self) -> List[dict]:
        """List all active products."""
        return [p for p in _products_store.values() if p.get("is_active", True)]
    
    def get_product(self, product_id: str) -> Optional[dict]:
        """Get product by ID."""
        return _products_store.get(product_id)


# Singleton
_cart_service: Optional[CartService] = None


def get_cart_service() -> CartService:
    """Get cart service instance."""
    global _cart_service
    if _cart_service is None:
        _cart_service = CartService()
    return _cart_service


def get_products_store() -> Dict[str, dict]:
    """Get products store for read access."""
    return _products_store
