"""
Cart Service — DB-backed

Manages shopping cart operations:
- Add/remove items
- Update quantities
- Apply coupons
- Calculate totals with tax and delivery
"""
import json
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

def _utcnow():
    return datetime.now(timezone.utc)


# ============ DATA CLASSES (unchanged API) ============

@dataclass
class CartItemData:
    id: str
    product_id: str
    variant_id: Optional[str]
    product_name: str
    product_type: str
    product_image: Optional[str]
    sku: Optional[str]
    quantity: int
    unit_price: int
    total_price: int
    tax_rate: float
    tax_amount: int
    scheduled_date: Optional[datetime] = None
    custom_options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CartData:
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
    valid: bool
    code: str
    discount_type: Optional[str] = None
    discount_value: Optional[int] = None
    discount_amount: int = 0
    error: Optional[str] = None


# ============ TAX CONFIGURATION ============
# NOTE: All product prices INCLUDE IVA (14%). Tax is not added on top.
# The tax_amount field represents the IVA portion already embedded in the price.
# Formula: tax_amount = price - price / (1 + tax_rate)

TAX_RATES = {
    "AO": 0.14,
    "PT": 0.23,
    "US": 0.0,
    "default": 0.14,
}


# ============ SECTOR LABELS ============

SECTOR_LABELS = {
    "mining": "Mineração",
    "infrastructure": "Construção e Infraestrutura",
    "agro": "Agro & Pecuária",
    "demining": "Desminagem Humanitária",
    "solar": "Solar & Energia",
    "livestock": "Pecuária",
}


# ============ SEED DATA ============

SHOP_PRODUCTS = [
    {"id": "prod_mining_volumetric", "name": "Voo Volumétrico de Mina", "slug": "voo-volumetrico-mina", "description": "Levantamento volumétrico de alta precisão para cálculo de stockpiles, cavas e movimentação de material.", "short_description": "Cálculo de volumes de stockpiles", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 95000000, "price_usd": 114500, "price_eur": 105500, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 72, "requires_site": True, "min_area_ha": 10, "sectors": ["mining"], "deliverables": ["Modelo 3D", "Relatório de Volume PDF", "Ortomosaico GeoTIFF", "Nuvem de Pontos LAS"], "image_url": "/assets/img/products/mining-volumetric.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_mining_topo_3d", "name": "Topografia 3D de Mina", "slug": "topografia-3d-mina", "description": "Mapeamento topográfico completo com LiDAR ou fotogrametria.", "short_description": "Topografia LiDAR/Fotogrametria", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 125000000, "price_usd": 150500, "price_eur": 138900, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 96, "requires_site": True, "min_area_ha": 20, "sectors": ["mining"], "deliverables": ["DTM/DEM", "Curvas de Nível", "Ortomosaico", "Relatório Técnico"], "image_url": "/assets/img/products/mining-topo.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_mining_slope_monitoring", "name": "Monitorização de Taludes", "slug": "monitorizacao-taludes", "description": "Análise de estabilidade de taludes com detecção de movimentação e riscos geotécnicos.", "short_description": "Estabilidade e risco geotécnico", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 65000000, "price_usd": 78500, "price_eur": 72200, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 48, "requires_site": True, "sectors": ["mining"], "deliverables": ["Mapa de Risco", "Análise de Deformação", "Relatório de Estabilidade"], "image_url": "/assets/img/products/mining-slope.jpg", "is_active": True},
    {"id": "prod_mining_environmental", "name": "Monitorização Ambiental Mineira", "slug": "monitorizacao-ambiental-mina", "description": "Monitorização de impacto ambiental: barragens de rejeitos, revegetação, qualidade de água.", "short_description": "Compliance ambiental", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 85000000, "price_usd": 102500, "price_eur": 94400, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 72, "requires_site": True, "sectors": ["mining"], "deliverables": ["Ortomosaico Multiespectral", "Relatório Ambiental", "Mapa de Vegetação"], "image_url": "/assets/img/products/mining-environmental.jpg", "is_active": True},
    {"id": "prod_infra_progress", "name": "Monitorização de Progresso de Obra", "slug": "monitorizacao-progresso-obra", "description": "Acompanhamento visual e volumétrico do progresso de construção.", "short_description": "Tracking de progresso de obra", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 55000000, "price_usd": 66500, "price_eur": 61100, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 48, "requires_site": True, "sectors": ["infrastructure", "construction"], "deliverables": ["Ortomosaico", "Modelo 3D", "Relatório de Progresso", "Vídeo Timelapse"], "image_url": "/assets/img/products/infra-progress.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_infra_earthworks", "name": "Análise de Earthworks", "slug": "analise-earthworks", "description": "Cálculo preciso de movimentação de terra: corte, aterro, compactação.", "short_description": "Corte & Aterro volumétrico", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 75000000, "price_usd": 90500, "price_eur": 83300, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 72, "requires_site": True, "sectors": ["infrastructure", "construction"], "deliverables": ["Relatório Cut/Fill", "Modelo 3D", "Comparação Design vs As-Built"], "image_url": "/assets/img/products/infra-earthworks.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_infra_digital_twin", "name": "Digital Twin de Infraestrutura", "slug": "digital-twin-infraestrutura", "description": "Modelo digital completo da infraestrutura para gestão de activos.", "short_description": "Gémeo digital completo", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 185000000, "price_usd": 223000, "price_eur": 205500, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 168, "requires_site": True, "sectors": ["infrastructure", "construction"], "deliverables": ["Modelo BIM", "Visualização 3D Web", "Plataforma de Gestão"], "image_url": "/assets/img/products/infra-digital-twin.jpg", "is_active": True},
    {"id": "prod_infra_inspection", "name": "Inspeção de Estruturas", "slug": "inspecao-estruturas", "description": "Inspeção visual detalhada de pontes, viadutos, torres e edifícios.", "short_description": "Inspeção de pontes e estruturas", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 45000000, "price_usd": 54500, "price_eur": 50000, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 24, "requires_site": True, "sectors": ["infrastructure"], "deliverables": ["Relatório de Inspeção", "Fotos HD Anotadas", "Vídeo 4K"], "image_url": "/assets/img/products/infra-inspection.jpg", "is_active": True},
    {"id": "prod_infra_corridor", "name": "Mapeamento de Corredores", "slug": "mapeamento-corredores", "description": "Mapeamento linear de estradas, pipelines, linhas de transmissão.", "short_description": "Estradas, pipelines, linhas TX", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 120000000, "price_usd": 144500, "price_eur": 133300, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 96, "requires_site": True, "sectors": ["infrastructure"], "deliverables": ["Ortomosaico Linear", "Perfil de Elevação", "Relatório de Condição"], "image_url": "/assets/img/products/infra-corridor.jpg", "is_active": True},
    {"id": "prod_agro_ndvi", "name": "Análise NDVI de Culturas", "slug": "analise-ndvi-culturas", "description": "Mapeamento multiespectral para análise da saúde de culturas com índice NDVI.", "short_description": "Saúde de culturas NDVI", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 45000000, "price_usd": 54500, "price_eur": 50000, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 48, "requires_site": True, "min_area_ha": 50, "sectors": ["agro"], "deliverables": ["Mapa NDVI", "Relatório de Saúde", "Zonas de Gestão"], "image_url": "/assets/img/products/agro-ndvi.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_agro_spraying", "name": "Pulverização de Precisão", "slug": "pulverizacao-precisao", "description": "Aplicação de precisão de fitofármacos, fertilizantes ou sementes por drone.", "short_description": "Spraying por drone", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 35000000, "price_usd": 42500, "price_eur": 38900, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 8, "requires_site": True, "min_area_ha": 20, "sectors": ["agro"], "deliverables": ["Relatório de Aplicação", "Mapa de Cobertura"], "image_url": "/assets/img/products/agro-spraying.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_agro_irrigation", "name": "Mapeamento de Irrigação", "slug": "mapeamento-irrigacao", "description": "Análise térmica e multiespectral para optimizar sistemas de irrigação.", "short_description": "Eficiência de irrigação", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 55000000, "price_usd": 66500, "price_eur": 61100, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 48, "requires_site": True, "sectors": ["agro"], "deliverables": ["Mapa Térmico", "Mapa de Stress Hídrico", "Recomendações"], "image_url": "/assets/img/products/agro-irrigation.jpg", "is_active": True},
    {"id": "prod_agro_livestock_count", "name": "Contagem de Gado por Drone", "slug": "contagem-gado-drone", "description": "Contagem automática de cabeças de gado com IA e visão computacional.", "short_description": "Contagem automática de gado", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 25000000, "price_usd": 30500, "price_eur": 27800, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 24, "requires_site": True, "sectors": ["agro", "livestock"], "deliverables": ["Relatório de Contagem", "Mapa de Distribuição", "Fotos Aéreas"], "image_url": "/assets/img/products/agro-livestock.jpg", "is_active": True},
    {"id": "prod_agro_land_survey", "name": "Levantamento Cadastral Agrícola", "slug": "levantamento-cadastral-agricola", "description": "Mapeamento e demarcação de propriedades agrícolas.", "short_description": "Demarcação de parcelas", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 65000000, "price_usd": 78500, "price_eur": 72200, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 72, "requires_site": True, "sectors": ["agro"], "deliverables": ["Ortomosaico", "Mapa Cadastral", "Relatório de Área"], "image_url": "/assets/img/products/agro-cadastral.jpg", "is_active": True},
    {"id": "prod_demining_thermal", "name": "Mapeamento Térmico para Desminagem", "slug": "mapeamento-termico-desminagem", "description": "Detecção de anomalias térmicas em terreno para identificar possíveis zonas minadas.", "short_description": "Detecção térmica de minas", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 75000000, "price_usd": 90500, "price_eur": 83300, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 48, "requires_site": True, "sectors": ["demining"], "deliverables": ["Mapa Térmico", "Mapa de Anomalias", "Relatório de Risco"], "image_url": "/assets/img/products/demining-thermal.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_demining_survey", "name": "Levantamento Pré-Desminagem", "slug": "levantamento-pre-desminagem", "description": "Mapeamento completo do terreno antes de operações de desminagem.", "short_description": "Survey pré-operacional", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 55000000, "price_usd": 66500, "price_eur": 61100, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 48, "requires_site": True, "sectors": ["demining"], "deliverables": ["Ortomosaico HD", "Modelo 3D Terreno", "Relatório de Condições"], "image_url": "/assets/img/products/demining-survey.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_demining_progress", "name": "Monitorização de Progresso de Desminagem", "slug": "monitorizacao-progresso-desminagem", "description": "Acompanhamento periódico do avanço das operações de desminagem.", "short_description": "Tracking de clearance", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 35000000, "price_usd": 42500, "price_eur": 38900, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 24, "requires_site": True, "sectors": ["demining"], "deliverables": ["Mapa de Progresso", "Relatório Semanal"], "image_url": "/assets/img/products/demining-progress.jpg", "is_active": True},
    {"id": "prod_solar_site_assessment", "name": "Avaliação de Terreno Solar", "slug": "avaliacao-terreno-solar", "description": "Análise topográfica e de irradiação para instalação de painéis solares.", "short_description": "Viabilidade solar", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 65000000, "price_usd": 78500, "price_eur": 72200, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 72, "requires_site": True, "sectors": ["solar"], "deliverables": ["Modelo 3D", "Análise de Sombreamento", "Relatório de Viabilidade"], "image_url": "/assets/img/products/solar-assessment.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_solar_panel_inspection", "name": "Inspeção Térmica de Painéis Solares", "slug": "inspecao-termica-paineis-solares", "description": "Detecção de hotspots e defeitos em painéis solares com câmara térmica.", "short_description": "Hotspot detection", "product_type": "service", "category": "flight", "execution_type": "recorrente", "price": 45000000, "price_usd": 54500, "price_eur": 50000, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 24, "requires_site": True, "sectors": ["solar"], "deliverables": ["Mapa Térmico", "Relatório de Defeitos", "Lista de Painéis Afectados"], "image_url": "/assets/img/products/solar-inspection.jpg", "is_active": True},
]

SHOP_COUPONS = [
    {"code": "WELCOME10", "discount_type": "percentage", "discount_value": 10, "minimum_order": 5000000, "usage_limit": 100, "first_order_only": True},
    {"code": "DRONE50K", "discount_type": "fixed", "discount_value": 5000000, "minimum_order": 50000000, "usage_limit": 50},
]


def seed_shop_products(db: Session) -> int:
    """Seed shop products and coupons into DB. Also syncs prices for existing products."""
    from app.models import ShopProduct, Coupon

    existing = db.query(ShopProduct.id).count()

    if existing > 0:
        # Sync prices and fields for existing products
        updated = 0
        seed_map = {p["id"]: p for p in SHOP_PRODUCTS}
        for sp in db.query(ShopProduct).all():
            src = seed_map.get(sp.id)
            if not src:
                continue
            changed = False
            # Always sync multi-currency prices from seed data
            if sp.price_usd != src.get("price_usd", 0):
                sp.price_usd = src.get("price_usd", 0)
                changed = True
            if sp.price_eur != src.get("price_eur", 0):
                sp.price_eur = src.get("price_eur", 0)
                changed = True
            if sp.price != src["price"]:
                sp.price = src["price"]
                changed = True
            if changed:
                updated += 1
        if updated:
            db.commit()
            logger.info(f"Synced prices for {updated} existing products")
        return 0

    count = 0
    for p in SHOP_PRODUCTS:
        sp = ShopProduct(
            id=p["id"], name=p["name"], slug=p["slug"],
            description=p.get("description"), short_description=p.get("short_description"),
            product_type=p.get("product_type", "service"), category=p.get("category", "flight"),
            execution_type=p.get("execution_type"), price=p["price"],
            price_usd=p.get("price_usd", 0), price_eur=p.get("price_eur", 0),
            currency=p.get("currency", "AOA"), tax_rate=p.get("tax_rate", 0.14),
            duration_hours=p.get("duration_hours"), requires_site=p.get("requires_site", False),
            min_area_ha=p.get("min_area_ha"),
            sectors_json=json.dumps(p.get("sectors", [])),
            deliverables_json=json.dumps(p.get("deliverables", [])),
            image_url=p.get("image_url"), is_active=p.get("is_active", True),
            is_featured=p.get("is_featured", False),
            track_inventory=p.get("track_inventory", False),
            stock_quantity=p.get("stock_quantity", 0),
        )
        db.add(sp)
        count += 1

    for c in SHOP_COUPONS:
        coupon = Coupon(
            code=c["code"], discount_type=c["discount_type"],
            discount_value=c["discount_value"],
            minimum_order=c.get("minimum_order", 0),
            usage_limit=c.get("usage_limit", 100),
            first_order_only=c.get("first_order_only", False),
        )
        db.add(coupon)

    db.commit()
    return count


# ============ CART SERVICE ============

class CartService:
    """Shopping cart service — DB-backed."""

    def __init__(self, db: Session):
        self.db = db

    def _models(self):
        from app.models import Cart as CartModel, CartItem as CartItemModel, ShopProduct, Coupon
        return CartModel, CartItemModel, ShopProduct, Coupon

    def get_or_create_cart(self, user_id=None, session_id=None, company_id=None):
        CM, _, _, _ = self._models()
        cart = None
        if user_id:
            cart = self.db.query(CM).filter(CM.user_id == user_id, CM.is_active == True).first()
        if not cart and session_id:
            cart = self.db.query(CM).filter(CM.session_id == session_id, CM.is_active == True).first()
        if cart:
            return self._to_data(cart)
        cart = CM(id=str(uuid.uuid4()), user_id=user_id, company_id=company_id,
                  session_id=session_id or str(uuid.uuid4()), currency="AOA",
                  is_active=True, expires_at=_utcnow() + timedelta(days=7))
        self.db.add(cart)
        self.db.commit()
        self.db.refresh(cart)
        return self._to_data(cart)

    def _find(self, cart_id):
        CM, _, _, _ = self._models()
        cart = self.db.get(CM, cart_id)
        if cart and cart.is_active:
            return cart
        return self.db.query(CM).filter(CM.session_id == cart_id, CM.is_active == True).first()

    def get_cart(self, cart_id): 
        c = self._find(cart_id)
        return self._to_data(c) if c else None

    def get_cart_by_session(self, session_id):
        CM = self._models()[0]
        c = self.db.query(CM).filter(CM.session_id == session_id, CM.is_active == True).first()
        return self._to_data(c) if c else None

    @staticmethod
    def _price_for_currency(product, currency="AOA"):
        """Return the correct price (centavos) for the given currency."""
        cur = (currency or "AOA").upper()
        if cur == "USD" and getattr(product, "price_usd", 0):
            return product.price_usd
        if cur == "EUR" and getattr(product, "price_eur", 0):
            return product.price_eur
        return product.price

    def add_item(self, cart_id, product_id, quantity=1, variant_id=None, scheduled_date=None, custom_options=None, currency=None):
        _, CIM, SP, _ = self._models()
        cart = self._find(cart_id)
        if not cart: raise ValueError("Cart not found")
        product = self.db.get(SP, product_id)
        if not product: raise ValueError("Product not found")
        if not product.is_active: raise ValueError("Product is not available")
        if product.track_inventory and product.stock_quantity < quantity:
            raise ValueError("Insufficient stock")
        # Use cart currency or the one provided
        cur = currency or cart.currency or "AOA"
        if currency and cart.currency != cur:
            cart.currency = cur
        existing = next((i for i in cart.cart_items if i.product_id == product_id and i.variant_id == variant_id), None)
        price = self._price_for_currency(product, cur)
        tax_rate = float(product.tax_rate)
        if existing:
            existing.quantity += quantity
            existing.total_price = existing.unit_price * existing.quantity
            # IVA is included in price: tax portion = price - price / (1 + rate)
            existing.tax_amount = int(existing.total_price - existing.total_price / (1 + tax_rate))
        else:
            total = price * quantity
            item = CIM(id=str(uuid.uuid4()), cart_id=cart.id, product_id=product_id,
                       variant_id=variant_id, product_name=product.name,
                       product_type=product.product_type, product_image=product.image_url,
                       sku=product.slug, quantity=quantity, unit_price=price,
                       total_price=total, tax_rate=tax_rate,
                       tax_amount=int(total - total / (1 + tax_rate)),
                       scheduled_date=scheduled_date,
                       custom_options_json=json.dumps(custom_options or {}))
            cart.cart_items.append(item)
        self._recalc(cart)
        self.db.commit(); self.db.refresh(cart)
        return self._to_data(cart)

    def update_item_quantity(self, cart_id, item_id, quantity):
        _, _, SP, _ = self._models()
        cart = self._find(cart_id)
        if not cart: raise ValueError("Cart not found")
        item = next((i for i in cart.cart_items if i.id == item_id), None)
        if not item: raise ValueError("Item not found in cart")
        if quantity <= 0:
            self.db.delete(item)
        else:
            p = self.db.get(SP, item.product_id)
            if p and p.track_inventory and p.stock_quantity < quantity:
                raise ValueError("Insufficient stock")
            item.quantity = quantity
            item.total_price = item.unit_price * quantity
            # IVA included: tax portion = price - price / (1 + rate)
            rate = float(item.tax_rate)
            item.tax_amount = int(item.total_price - item.total_price / (1 + rate))
        self._recalc(cart)
        self.db.commit(); self.db.refresh(cart)
        return self._to_data(cart)

    def remove_item(self, cart_id, item_id):
        return self.update_item_quantity(cart_id, item_id, 0)

    def update_currency(self, cart_id, new_currency):
        """Change the cart currency and recalculate all item prices."""
        _, _, SP, _ = self._models()
        cart = self._find(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        cur = (new_currency or "AOA").upper()
        if cur not in ("AOA", "USD", "EUR"):
            raise ValueError(f"Moeda inválida: {cur}")
        cart.currency = cur
        for item in cart.cart_items:
            product = self.db.get(SP, item.product_id)
            if product:
                new_price = self._price_for_currency(product, cur)
                item.unit_price = new_price
                item.total_price = new_price * item.quantity
                # IVA included: tax portion = price - price / (1 + rate)
                rate = float(item.tax_rate)
                item.tax_amount = int(item.total_price - item.total_price / (1 + rate))
        self._recalc(cart)
        self.db.commit()
        self.db.refresh(cart)
        return self._to_data(cart)

    def apply_coupon(self, cart_id, coupon_code):
        _, _, _, CouponM = self._models()
        cart = self._find(cart_id)
        if not cart: return CouponValidation(valid=False, code=coupon_code, error="Cart not found")
        code = coupon_code.upper().strip()
        coupon = self.db.query(CouponM).filter(CouponM.code == code, CouponM.is_active == True).first()
        if not coupon: return CouponValidation(valid=False, code=coupon_code, error="Cupão inválido")
        if coupon.usage_limit and coupon.usage_count >= coupon.usage_limit:
            return CouponValidation(valid=False, code=coupon_code, error="Cupão esgotado")
        subtotal = cart.subtotal or 0
        if coupon.minimum_order and subtotal < coupon.minimum_order:
            return CouponValidation(valid=False, code=coupon_code, error=f"Pedido mínimo de {coupon.minimum_order/100:,.0f} AOA")
        if coupon.discount_type == "percentage":
            da = int(subtotal * coupon.discount_value / 100)
            if coupon.maximum_discount: da = min(da, coupon.maximum_discount)
        else:
            da = coupon.discount_value
        cart.coupon_code = code; cart.discount_type = coupon.discount_type; cart.discount_amount = da
        self._recalc(cart); self.db.commit()
        return CouponValidation(valid=True, code=code, discount_type=coupon.discount_type, discount_value=coupon.discount_value, discount_amount=da)

    def remove_coupon(self, cart_id):
        cart = self._find(cart_id)
        if not cart: raise ValueError("Cart not found")
        cart.coupon_code = None; cart.discount_type = None; cart.discount_amount = 0
        self._recalc(cart); self.db.commit(); self.db.refresh(cart)
        return self._to_data(cart)

    def set_delivery(self, cart_id, delivery_method, delivery_address=None):
        cart = self._find(cart_id)
        if not cart: raise ValueError("Cart not found")
        costs = {"pickup": 0, "luanda": 500000, "provinces": 1500000, "international": 5000000}
        cart.delivery_method = delivery_method
        cart.delivery_cost = costs.get(delivery_method, 0)
        cart.delivery_address_json = json.dumps(delivery_address) if delivery_address else None
        self._recalc(cart); self.db.commit(); self.db.refresh(cart)
        return self._to_data(cart)

    def set_site(self, cart_id, site_id):
        cart = self._find(cart_id)
        if not cart: raise ValueError("Cart not found")
        cart.site_id = site_id; cart.updated_at = _utcnow()
        self.db.commit(); self.db.refresh(cart)
        return self._to_data(cart)

    def clear_cart(self, cart_id):
        _, CIM, _, _ = self._models()
        cart = self._find(cart_id)
        if not cart: return False
        self.db.query(CIM).filter(CIM.cart_id == cart.id).delete()
        cart.coupon_code = None; cart.discount_amount = 0; cart.discount_type = None
        self._recalc(cart); self.db.commit()
        return True

    def _recalc(self, cart):
        """Recalculate cart totals. Prices already include IVA — tax is NOT added on top."""
        items = cart.cart_items
        cart.subtotal = sum(i.total_price for i in items)
        cart.tax_amount = sum(i.tax_amount for i in items)  # IVA portion already inside subtotal
        cart.total = max(0, cart.subtotal - (cart.discount_amount or 0) + (cart.delivery_cost or 0))
        cart.updated_at = _utcnow()

    def _to_data(self, cart):
        items = [CartItemData(id=i.id, product_id=i.product_id, variant_id=i.variant_id,
                    product_name=i.product_name, product_type=i.product_type,
                    product_image=i.product_image, sku=i.sku, quantity=i.quantity,
                    unit_price=i.unit_price, total_price=i.total_price,
                    tax_rate=float(i.tax_rate), tax_amount=i.tax_amount,
                    scheduled_date=i.scheduled_date,
                    custom_options=json.loads(i.custom_options_json or "{}"))
                 for i in cart.cart_items]
        return CartData(id=cart.id, user_id=cart.user_id, company_id=cart.company_id,
            session_id=cart.session_id, site_id=cart.site_id, items=items,
            item_count=len(items), subtotal=cart.subtotal or 0,
            discount_amount=cart.discount_amount or 0, discount_type=cart.discount_type,
            coupon_code=cart.coupon_code, tax_rate=0.14, tax_amount=cart.tax_amount or 0,
            delivery_cost=cart.delivery_cost or 0, delivery_method=cart.delivery_method,
            total=cart.total or 0, currency=cart.currency or "AOA",
            created_at=cart.created_at or _utcnow(), updated_at=cart.updated_at or _utcnow())

    def list_products(self):
        SP = self._models()[2]
        return [self._p2d(p) for p in self.db.query(SP).filter(SP.is_active == True).all()]

    def get_product(self, product_id):
        SP = self._models()[2]
        p = self.db.get(SP, product_id)
        return self._p2d(p) if p else None

    def _p2d(self, p):
        return {"id": p.id, "name": p.name, "slug": p.slug, "description": p.description,
                "short_description": p.short_description, "product_type": p.product_type,
                "category": p.category, "execution_type": p.execution_type, "price": p.price,
                "price_usd": p.price_usd, "price_eur": p.price_eur,
                "currency": p.currency, "tax_rate": float(p.tax_rate),
                "duration_hours": p.duration_hours, "requires_site": p.requires_site,
                "min_area_ha": p.min_area_ha, "sectors": json.loads(p.sectors_json or "[]"),
                "deliverables": json.loads(p.deliverables_json or "[]"),
                "image_url": p.image_url, "is_active": p.is_active, "is_featured": p.is_featured,
                "track_inventory": p.track_inventory, "stock_quantity": p.stock_quantity,
                "created_at": p.created_at, "updated_at": p.updated_at}

    def check_sector_mismatch(self, product_id, account_sector):
        if not account_sector: return None
        product = self.get_product(product_id)
        if not product: return None
        sectors = product.get("sectors", [])
        if not sectors or account_sector in sectors: return None
        pl = SECTOR_LABELS.get(sectors[0], sectors[0])
        al = SECTOR_LABELS.get(account_sector, account_sector)
        return {"warning": True, "sector_mismatch": True, "product_sector": sectors[0],
                "product_sector_label": pl, "account_sector": account_sector,
                "account_sector_label": al,
                "message": f"Este serviço é destinado ao sector {pl}. A sua conta está configurada para {al}.",
                "suggestion": f"Pode continuar com a compra ou criar uma nova conta {pl}."}

    def get_cart_with_warnings(self, cart_id, account_sector=None):
        cart = self._find(cart_id)
        if not cart: raise ValueError("Cart not found")
        cd = self._to_data(cart)
        items_w = []; hw = False
        for item in cd.items:
            w = self.check_sector_mismatch(item.product_id, account_sector)
            if w: hw = True
            items_w.append({"id": item.id, "product_id": item.product_id, "product_name": item.product_name,
                "product_type": item.product_type, "quantity": item.quantity, "unit_price": item.unit_price,
                "total_price": item.total_price, "tax_amount": item.tax_amount,
                "product_image": item.product_image, "warning": w})
        return {"cart": {"id": cd.id, "user_id": cd.user_id, "item_count": cd.item_count,
            "subtotal": cd.subtotal, "discount_amount": cd.discount_amount, "tax_amount": cd.tax_amount,
            "delivery_cost": cd.delivery_cost, "total": cd.total, "currency": cd.currency},
            "items": items_w, "has_sector_warnings": hw}


def get_sector_labels():
    return SECTOR_LABELS.copy()

def get_cart_service(db: Session) -> CartService:
    return CartService(db)
