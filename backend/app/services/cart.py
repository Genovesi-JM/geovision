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
from app.product_translations import get_product_translations
from app.account_profiles import normalize_public_sector

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
    "environment": "Ambiental & Propriedades",
    "mining": "Mineração",
    "infrastructure": "Construção e Infraestrutura",
    "construction": "Construção",
    "industry": "Indústria e Mineração",
    "agro": "Agro & Pecuária",
    "home": "Casa",
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

# Current public offer. Older sector-specific and specialist services remain in
# SHOP_PRODUCTS as standby definitions, but are not advertised until a validated
# project justifies rental, partnership or specialist delivery.
SHOP_PRODUCTS += [
    {"id": "prod_aerial_basic_mapping", "name": "Mapeamento Aéreo Essencial", "slug": "mapeamento-aereo-essencial", "description": "Mapeamento visual de uma quinta, propriedade ou local com ortomosaico e resumo de observações.", "short_description": "Mapa visual e documentação do local", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 35000000, "price_usd": 42500, "price_eur": 38900, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 24, "requires_site": True, "sectors": ["agro", "infrastructure", "environment"], "deliverables": ["Ortomosaico visual", "Fotografias georreferenciadas", "Resumo de observações"], "image_url": "/assets/img/products/agro-cadastral.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_agro_visual_inspection", "name": "Inspeção Visual Agrícola", "slug": "inspecao-visual-agricola", "description": "Inspeção aérea visual para documentar culturas, irrigação, acessos e anomalias visíveis sem prometer análise multiespectral.", "short_description": "Observação visual e registo da exploração", "product_type": "service", "category": "flight", "execution_type": "pontual", "price": 25000000, "price_usd": 30500, "price_eur": 27800, "currency": "AOA", "tax_rate": 0.14, "duration_hours": 24, "requires_site": True, "sectors": ["agro"], "deliverables": ["Fotografias aéreas", "Mapa de observações", "Relatório visual"], "image_url": "/assets/img/products/agro-ndvi.jpg", "is_active": True, "is_featured": True},
    {"id": "prod_supply_soil_probe", "name": "Kit de Sondas de Solo", "slug": "kit-sondas-solo", "description": "Sondas de humidade do solo para substituição, expansão ou primeiro protótipo GeoVision. Fornecimento sujeito a confirmação de compatibilidade.", "short_description": "Sondas para medir humidade do solo", "product_type": "hardware", "category": "sensor", "price": 2550000, "price_usd": 3000, "price_eur": 2800, "currency": "AOA", "tax_rate": 0.14, "requires_site": False, "sectors": ["agro"], "deliverables": ["2 sondas capacitivas", "Guia de ligação", "Verificação de compatibilidade"], "image_url": None, "is_active": True},
    {"id": "prod_supply_irrigation_parts", "name": "Kit de Componentes de Irrigação", "slug": "kit-componentes-irrigacao", "description": "Conjunto inicial de válvula de baixa tensão, sensor de caudal e conectores para um protótipo de irrigação monitorizada.", "short_description": "Válvula, caudal e ligações para protótipo", "product_type": "hardware", "category": "irrigation", "price": 4250000, "price_usd": 5000, "price_eur": 4600, "currency": "AOA", "tax_rate": 0.14, "requires_site": False, "sectors": ["agro", "home"], "deliverables": ["Válvula de baixa tensão", "Sensor de caudal", "Conectores e guia"], "image_url": None, "is_active": True},
    {"id": "prod_supply_monitoring_spares", "name": "Pack de Acessórios para Sensores", "slug": "pack-acessorios-sensores", "description": "Cabos, conectores, prensa-cabos e pequenos consumíveis para manutenção de um nó GeoVision.", "short_description": "Peças pequenas para instalar e manter sensores", "product_type": "hardware", "category": "accessory", "price": 2125000, "price_usd": 2500, "price_eur": 2300, "currency": "AOA", "tax_rate": 0.14, "requires_site": False, "sectors": ["home", "agro", "infrastructure", "environment"], "deliverables": ["Cabos e conectores", "Prensa-cabos", "Consumíveis de instalação"], "image_url": None, "is_active": True},
    {"id": "prod_supply_weather_pack", "name": "Pack de Sensores Meteorológicos", "slug": "pack-sensores-meteorologicos", "description": "Sensores de temperatura, humidade e chuva para protótipos de campo e pequenas estações meteorológicas.", "short_description": "Temperatura, humidade e chuva", "product_type": "hardware", "category": "sensor", "price": 7650000, "price_usd": 9000, "price_eur": 8300, "currency": "AOA", "tax_rate": 0.14, "requires_site": False, "sectors": ["agro", "environment"], "deliverables": ["Sensor de temperatura/humidade", "Pluviómetro", "Guia de protótipo"], "image_url": None, "is_active": True},
]

_PUBLIC_STATIC_PRODUCT_IDS = {
    "prod_infra_progress",
    "prod_infra_inspection",
    "prod_aerial_basic_mapping",
    "prod_agro_visual_inspection",
    "prod_supply_soil_probe",
    "prod_supply_irrigation_parts",
    "prod_supply_monitoring_spares",
    "prod_supply_weather_pack",
}

SHOP_COUPONS = [
    {"code": "WELCOME10", "discount_type": "percentage", "discount_value": 10, "minimum_order": 5000000, "usage_limit": 100, "first_order_only": True},
    {"code": "DRONE50K", "discount_type": "fixed", "discount_value": 5000000, "minimum_order": 50000000, "usage_limit": 50},
]


def seed_shop_products(db: Session) -> int:
    """Upsert the controlled catalogue and keep standby products off the storefront."""
    from app.models import ShopProduct, Coupon

    count = 0
    for p in SHOP_PRODUCTS:
        sp = db.get(ShopProduct, p["id"])
        if sp is None:
            sp = ShopProduct(id=p["id"], slug=p["slug"], name=p["name"])
            db.add(sp)
            count += 1
        sp.name = p["name"]
        sp.slug = p["slug"]
        sp.description = p.get("description")
        sp.short_description = p.get("short_description")
        sp.product_type = p.get("product_type", "service")
        sp.category = p.get("category", "flight")
        sp.execution_type = p.get("execution_type")
        sp.price = p["price"]
        sp.price_usd = p.get("price_usd", 0)
        sp.price_eur = p.get("price_eur", 0)
        sp.currency = p.get("currency", "AOA")
        sp.tax_rate = p.get("tax_rate", 0.14)
        sp.duration_hours = p.get("duration_hours")
        sp.requires_site = p.get("requires_site", False)
        sp.min_area_ha = p.get("min_area_ha")
        sp.sectors_json = json.dumps(p.get("sectors", []))
        sp.deliverables_json = json.dumps(p.get("deliverables", []))
        sp.image_url = p.get("image_url")
        sp.is_active = p["id"] in _PUBLIC_STATIC_PRODUCT_IDS
        sp.is_featured = p.get("is_featured", False) and sp.is_active
        sp.track_inventory = p.get("track_inventory", False)
        sp.stock_quantity = p.get("stock_quantity", 0)

    for c in SHOP_COUPONS:
        coupon = db.query(Coupon).filter(Coupon.code == c["code"]).first()
        if coupon is None:
            coupon = Coupon(code=c["code"], discount_type=c["discount_type"], discount_value=c["discount_value"])
            db.add(coupon)
        coupon.minimum_order = c.get("minimum_order", 0)
        coupon.usage_limit = c.get("usage_limit", 100)
        coupon.first_order_only = c.get("first_order_only", False)

    db.commit()
    return count


# Map active DIY kit industries onto the store sectors where the kit is useful.
# Home follows the supported property use cases: air/comfort, water and leaks.
_KIT_SECTORS = {
    "agriculture": ["agro"],
    "environment": ["home", "environment"],
    "water": ["home", "infrastructure"],
    "energy": ["infrastructure"],
    "facilities": ["home", "infrastructure"],
    "cold_chain": ["infrastructure"],
}

# Preserve the kit definition for possible future/on-request work, but do not
# advertise unsupported monitoring products in the public marketplace.
_MARKETPLACE_EXCLUDED_KITS = {
    "energy_meter_starter",
    "cold_chain_starter",
    "spray_control",
    "seed_flow",
}


def seed_kit_products(db: Session) -> int:
    """Surface DIY solution kits in the existing marketplace as hardware products.

    Idempotent upsert (by id) that runs on every startup so kits appear even on a
    pre-existing product catalogue. Reuses the ShopProduct catalogue — no new
    storefront. Prices are DIY-kit estimates; AOA/EUR are derived from the USD figure.
    """
    from app.models import ShopProduct
    from app.iot.kits import list_kits

    upserted = 0
    for kit in list_kits(include_standby=True):
        pid = f"prod_kit_{kit['id']}"[:50]
        if kit["id"] in _MARKETPLACE_EXCLUDED_KITS:
            existing = db.get(ShopProduct, pid)
            if existing is not None:
                existing.is_active = False
            continue
        # Store prices are held in minor units (×100), matching existing products.
        usd = int(kit.get("price_usd", 0))
        price_usd = usd * 100
        price_aoa = usd * 850 * 100
        price_eur = round(usd * 0.92) * 100
        sectors = _KIT_SECTORS.get(kit.get("industry"), ["infrastructure"])
        deliverables = list(kit.get("kpis", [])) + ["Live dashboard", "Threshold alerts", "PDF/CSV analytical reports"]
        desc = kit.get("summary", "") + " Dispositivo GeoVision de monitorização, pronto a instalar. Inclui: " + ", ".join(item["part"] for item in kit.get("diy_bom", []))
        sp = db.get(ShopProduct, pid)
        if sp is None:
            sp = ShopProduct(id=pid, slug=f"diy-kit-{kit['id']}".replace("_", "-"), name=kit["name"])
            db.add(sp)
            upserted += 1
        localized = get_product_translations(pid).get("pt", {})
        sp.name = localized.get("name", kit["name"])
        sp.description = localized.get("description", desc)[:2000]
        sp.short_description = localized.get("short_description", kit.get("summary", ""))[:500]
        sp.product_type = "hardware"
        sp.category = "sensor_kit"
        sp.price = price_aoa
        sp.price_usd = price_usd
        sp.price_eur = price_eur
        sp.currency = "AOA"
        sp.sectors_json = json.dumps(sectors)
        sp.deliverables_json = json.dumps(deliverables)
        sp.is_active = True
        sp.track_inventory = False
    db.commit()
    return upserted


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
                "translations": get_product_translations(p.id),
                "image_url": p.image_url, "is_active": p.is_active, "is_featured": p.is_featured,
                "track_inventory": p.track_inventory, "stock_quantity": p.stock_quantity,
                "created_at": p.created_at, "updated_at": p.updated_at}

    def check_sector_mismatch(self, product_id, account_sector):
        if not account_sector: return None
        product = self.get_product(product_id)
        if not product: return None
        sectors = product.get("sectors", [])
        def current_sector(value):
            return normalize_public_sector(value)
        account_sector = current_sector(account_sector)
        normalized_sectors = [current_sector(s) for s in sectors]
        if not sectors or account_sector in normalized_sectors: return None
        product_sector = normalized_sectors[0]
        pl = SECTOR_LABELS.get(product_sector, product_sector)
        al = SECTOR_LABELS.get(account_sector, account_sector)
        return {"warning": True, "sector_mismatch": True, "product_sector": product_sector,
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
