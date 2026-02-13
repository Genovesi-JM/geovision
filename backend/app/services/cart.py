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


# ============ SECTOR LABELS ============

SECTOR_LABELS = {
    "mining": "Mineração",
    "infrastructure": "Construção e Infraestrutura",
    "agro": "Agro & Pecuária",
    "demining": "Desminagem Humanitária",
    "solar": "Solar & Energia",
    "livestock": "Pecuária",
}


# ============ SEED DEMO PRODUCTS ============

def seed_demo_products():
    """Seed comprehensive flight services for all sectors."""
    products = [
        # ==========================================
        # MINING SECTOR
        # ==========================================
        {
            "id": "prod_mining_volumetric",
            "name": "Voo Volumétrico de Mina",
            "slug": "voo-volumetrico-mina",
            "description": "Levantamento volumétrico de alta precisão para cálculo de stockpiles, cavas e movimentação de material. Entrega: Modelo 3D, Relatório de Volume, Ortomosaico.",
            "short_description": "Cálculo de volumes de stockpiles",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 95000000,  # 950.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "min_area_ha": 10,
            "sectors": ["mining"],
            "deliverables": ["Modelo 3D", "Relatório de Volume PDF", "Ortomosaico GeoTIFF", "Nuvem de Pontos LAS"],
            "image_url": "/assets/img/products/mining-volumetric.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_mining_topo_3d",
            "name": "Topografia 3D de Mina",
            "slug": "topografia-3d-mina",
            "description": "Mapeamento topográfico completo com LiDAR ou fotogrametria. Ideal para planeamento de escavação e conformidade regulatória.",
            "short_description": "Topografia LiDAR/Fotogrametria",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 125000000,  # 1.250.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 96,
            "requires_site": True,
            "min_area_ha": 20,
            "sectors": ["mining"],
            "deliverables": ["DTM/DEM", "Curvas de Nível", "Ortomosaico", "Relatório Técnico"],
            "image_url": "/assets/img/products/mining-topo.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_mining_slope_monitoring",
            "name": "Monitorização de Taludes",
            "slug": "monitorizacao-taludes",
            "description": "Análise de estabilidade de taludes com detecção de movimentação e riscos geotécnicos. Serviço recorrente recomendado.",
            "short_description": "Estabilidade e risco geotécnico",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 65000000,  # 650.000 AOA por voo
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "sectors": ["mining"],
            "deliverables": ["Mapa de Risco", "Análise de Deformação", "Relatório de Estabilidade"],
            "image_url": "/assets/img/products/mining-slope.jpg",
            "is_active": True,
        },
        {
            "id": "prod_mining_environmental",
            "name": "Monitorização Ambiental Mineira",
            "slug": "monitorizacao-ambiental-mina",
            "description": "Monitorização de impacto ambiental: barragens de rejeitos, revegetação, qualidade de água.",
            "short_description": "Compliance ambiental",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 85000000,  # 850.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "sectors": ["mining"],
            "deliverables": ["Ortomosaico Multiespectral", "Relatório Ambiental", "Mapa de Vegetação"],
            "image_url": "/assets/img/products/mining-environmental.jpg",
            "is_active": True,
        },
        
        # ==========================================
        # INFRASTRUCTURE / CONSTRUCTION SECTOR
        # ==========================================
        {
            "id": "prod_infra_progress",
            "name": "Monitorização de Progresso de Obra",
            "slug": "monitorizacao-progresso-obra",
            "description": "Acompanhamento visual e volumétrico do progresso de construção. Ideal para relatórios a stakeholders e conformidade.",
            "short_description": "Tracking de progresso de obra",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 55000000,  # 550.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "sectors": ["infrastructure", "construction"],
            "deliverables": ["Ortomosaico", "Modelo 3D", "Relatório de Progresso", "Vídeo Timelapse"],
            "image_url": "/assets/img/products/infra-progress.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_infra_earthworks",
            "name": "Análise de Earthworks",
            "slug": "analise-earthworks",
            "description": "Cálculo preciso de movimentação de terra: corte, aterro, compactação. Comparação com projecto original.",
            "short_description": "Corte & Aterro volumétrico",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 75000000,  # 750.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "sectors": ["infrastructure", "construction"],
            "deliverables": ["Relatório Cut/Fill", "Modelo 3D", "Comparação Design vs As-Built"],
            "image_url": "/assets/img/products/infra-earthworks.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_infra_digital_twin",
            "name": "Digital Twin de Infraestrutura",
            "slug": "digital-twin-infraestrutura",
            "description": "Modelo digital completo da infraestrutura para gestão de activos, planeamento e manutenção.",
            "short_description": "Gémeo digital completo",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 185000000,  # 1.850.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 168,
            "requires_site": True,
            "sectors": ["infrastructure", "construction"],
            "deliverables": ["Modelo BIM", "Visualização 3D Web", "Plataforma de Gestão"],
            "image_url": "/assets/img/products/infra-digital-twin.jpg",
            "is_active": True,
        },
        {
            "id": "prod_infra_inspection",
            "name": "Inspeção de Estruturas",
            "slug": "inspecao-estruturas",
            "description": "Inspeção visual detalhada de pontes, viadutos, torres e edifícios. Detecção de fissuras e degradação.",
            "short_description": "Inspeção de pontes e estruturas",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 45000000,  # 450.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 24,
            "requires_site": True,
            "sectors": ["infrastructure"],
            "deliverables": ["Relatório de Inspeção", "Fotos HD Anotadas", "Vídeo 4K"],
            "image_url": "/assets/img/products/infra-inspection.jpg",
            "is_active": True,
        },
        {
            "id": "prod_infra_corridor",
            "name": "Mapeamento de Corredores",
            "slug": "mapeamento-corredores",
            "description": "Mapeamento linear de estradas, pipelines, linhas de transmissão. Até 100km por missão.",
            "short_description": "Estradas, pipelines, linhas TX",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 120000000,  # 1.200.000 AOA por 50km
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 96,
            "requires_site": True,
            "sectors": ["infrastructure"],
            "deliverables": ["Ortomosaico Linear", "Perfil de Elevação", "Relatório de Condição"],
            "image_url": "/assets/img/products/infra-corridor.jpg",
            "is_active": True,
        },
        
        # ==========================================
        # AGRICULTURE & LIVESTOCK SECTOR
        # ==========================================
        {
            "id": "prod_agro_ndvi",
            "name": "Análise NDVI Agrícola",
            "slug": "analise-ndvi-agricola",
            "description": "Mapeamento de saúde vegetal com índice NDVI. Detecção de stress hídrico, pragas e deficiências nutricionais.",
            "short_description": "NDVI saúde vegetal",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 25000000,  # 250.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "min_area_ha": 20,
            "sectors": ["agro"],
            "deliverables": ["Mapa NDVI", "Relatório de Saúde", "Zonas de Gestão", "Recomendações"],
            "image_url": "/assets/img/products/agro-ndvi.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_agro_spraying",
            "name": "Pulverização por Drone",
            "slug": "pulverizacao-drone",
            "description": "Aplicação precisa de fitossanitários, fertilizantes ou sementes com drones DJI Agras. Até 100ha/dia.",
            "short_description": "Pulverização até 100ha/dia",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 5000000,  # 50.000 AOA por hectare
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 8,
            "requires_site": True,
            "requires_scheduling": True,
            "min_area_ha": 5,
            "sectors": ["agro"],
            "deliverables": ["Relatório de Aplicação", "Mapa de Cobertura", "Certificado"],
            "image_url": "/assets/img/products/agro-spraying.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_agro_livestock_count",
            "name": "Contagem de Rebanho",
            "slug": "contagem-rebanho",
            "description": "Contagem automática de gado com IA. Ideal para fazendas de grande escala e gestão de inventário.",
            "short_description": "Contagem automática de gado",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 35000000,  # 350.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 24,
            "requires_site": True,
            "sectors": ["agro", "livestock"],
            "deliverables": ["Relatório de Contagem", "Mapa de Distribuição", "Vídeo HD"],
            "image_url": "/assets/img/products/agro-livestock.jpg",
            "is_active": True,
        },
        {
            "id": "prod_agro_irrigation",
            "name": "Análise de Irrigação",
            "slug": "analise-irrigacao",
            "description": "Mapeamento térmico para detecção de falhas de irrigação, fugas e optimização de recursos hídricos.",
            "short_description": "Thermal irrigation analysis",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 45000000,  # 450.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "sectors": ["agro"],
            "deliverables": ["Mapa Térmico", "Relatório de Irrigação", "Recomendações"],
            "image_url": "/assets/img/products/agro-irrigation.jpg",
            "is_active": True,
        },
        {
            "id": "prod_agro_crop_mapping",
            "name": "Mapeamento de Culturas",
            "slug": "mapeamento-culturas",
            "description": "Classificação e mapeamento de diferentes culturas. Estimativa de produtividade e planeamento de colheita.",
            "short_description": "Classificação de culturas",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 55000000,  # 550.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "min_area_ha": 50,
            "sectors": ["agro"],
            "deliverables": ["Mapa de Culturas", "Estimativa de Produção", "Ortomosaico"],
            "image_url": "/assets/img/products/agro-crop-mapping.jpg",
            "is_active": True,
        },
        {
            "id": "prod_agro_monitoring_sub",
            "name": "Monitorização Agrícola Mensal",
            "slug": "monitorizacao-agricola-mensal",
            "description": "Assinatura mensal com 2 voos NDVI, alertas automáticos e relatórios de evolução.",
            "short_description": "2 voos/mês + alertas",
            "product_type": "subscription",
            "category": "monitoring",
            "execution_type": "recorrente",
            "price": 45000000,  # 450.000 AOA/mês
            "currency": "AOA",
            "tax_rate": 0.14,
            "requires_site": True,
            "sectors": ["agro"],
            "deliverables": ["Voos Mensais", "Relatórios", "Alertas", "Dashboard"],
            "image_url": "/assets/img/products/agro-monitoring.jpg",
            "is_active": True,
            "is_featured": True,
        },
        
        # ==========================================
        # DEMINING SECTOR
        # ==========================================
        {
            "id": "prod_demining_thermal",
            "name": "Mapeamento Térmico para Desminagem",
            "slug": "mapeamento-termico-desminagem",
            "description": "Detecção de anomalias térmicas no solo que podem indicar presença de objectos enterrados. Suporte a operações de limpeza.",
            "short_description": "Detecção térmica de anomalias",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 85000000,  # 850.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "sectors": ["demining"],
            "deliverables": ["Mapa Térmico", "Mapa de Anomalias", "Relatório de Risco", "Coordenadas GPS"],
            "image_url": "/assets/img/products/demining-thermal.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_demining_multispectral",
            "name": "Análise Multiespectral de Solo",
            "slug": "analise-multiespectral-desminagem",
            "description": "Detecção de alterações no solo usando sensores multiespectrais. Identificação de áreas de risco para equipas de desminagem.",
            "short_description": "Multiespectral solo alterado",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 95000000,  # 950.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 96,
            "requires_site": True,
            "sectors": ["demining"],
            "deliverables": ["Análise Espectral", "Mapa de Risco", "Relatório Técnico"],
            "image_url": "/assets/img/products/demining-multispectral.jpg",
            "is_active": True,
        },
        {
            "id": "prod_demining_baseline",
            "name": "Mapeamento Baseline de Área Contaminada",
            "slug": "mapeamento-baseline-desminagem",
            "description": "Ortomosaico e modelo 3D de alta resolução para planeamento de operações de desminagem e documentação.",
            "short_description": "Baseline ortomosaico 3D",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 65000000,  # 650.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "sectors": ["demining"],
            "deliverables": ["Ortomosaico HD", "Modelo 3D", "Mapa de Planeamento"],
            "image_url": "/assets/img/products/demining-baseline.jpg",
            "is_active": True,
        },
        {
            "id": "prod_demining_progress",
            "name": "Monitorização de Progresso de Limpeza",
            "slug": "monitorizacao-progresso-desminagem",
            "description": "Acompanhamento visual do progresso de desminagem para relatórios a doadores e stakeholders.",
            "short_description": "Tracking de limpeza",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 45000000,  # 450.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 24,
            "requires_site": True,
            "sectors": ["demining"],
            "deliverables": ["Ortomosaico", "Relatório de Progresso", "Comparativo Temporal"],
            "image_url": "/assets/img/products/demining-progress.jpg",
            "is_active": True,
        },
        
        # ==========================================
        # SOLAR & ENERGY SECTOR
        # ==========================================
        {
            "id": "prod_solar_thermal_inspection",
            "name": "Inspeção Térmica de Painéis Solares",
            "slug": "inspecao-termica-solar",
            "description": "Detecção de hotspots, células defeituosas e anomalias em parques solares usando câmaras térmicas de alta resolução.",
            "short_description": "Thermal inspection painéis",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 55000000,  # 550.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 48,
            "requires_site": True,
            "sectors": ["solar"],
            "deliverables": ["Mapa Térmico", "Relatório de Defeitos", "Lista de Painéis Afectados", "Recomendações"],
            "image_url": "/assets/img/products/solar-thermal.jpg",
            "is_active": True,
            "is_featured": True,
        },
        {
            "id": "prod_solar_monitoring",
            "name": "Monitorização de Parque Solar",
            "slug": "monitorizacao-parque-solar",
            "description": "Monitorização regular de parques fotovoltaicos com análise de performance e detecção precoce de problemas.",
            "short_description": "Monitoring recorrente solar",
            "product_type": "service",
            "category": "flight",
            "execution_type": "recorrente",
            "price": 75000000,  # 750.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "sectors": ["solar"],
            "deliverables": ["Relatório de Performance", "Análise de Degradação", "Mapa de Sujidade"],
            "image_url": "/assets/img/products/solar-monitoring.jpg",
            "is_active": True,
        },
        {
            "id": "prod_solar_site_assessment",
            "name": "Avaliação de Terreno para Solar",
            "slug": "avaliacao-terreno-solar",
            "description": "Análise topográfica e de sombreamento para planeamento de novos parques solares.",
            "short_description": "Site assessment solar",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 95000000,  # 950.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 96,
            "requires_site": True,
            "sectors": ["solar"],
            "deliverables": ["Modelo 3D", "Análise de Sombreamento", "Estudo de Viabilidade"],
            "image_url": "/assets/img/products/solar-site.jpg",
            "is_active": True,
        },
        {
            "id": "prod_energy_transmission",
            "name": "Inspeção de Linhas de Transmissão",
            "slug": "inspecao-linhas-transmissao",
            "description": "Inspeção visual e térmica de linhas de transmissão elétrica. Detecção de danos, vegetação invasora e pontos quentes.",
            "short_description": "Inspeção linhas TX elétrica",
            "product_type": "service",
            "category": "flight",
            "execution_type": "pontual",
            "price": 125000000,  # 1.250.000 AOA por 50km
            "currency": "AOA",
            "tax_rate": 0.14,
            "duration_hours": 72,
            "requires_site": True,
            "sectors": ["solar", "infrastructure"],
            "deliverables": ["Relatório de Inspeção", "Mapa de Defeitos", "Vídeo HD", "Fotos Anotadas"],
            "image_url": "/assets/img/products/energy-transmission.jpg",
            "is_active": True,
        },
        
        # ==========================================
        # HARDWARE & SUPPLIES (Multi-sector)
        # ==========================================
        {
            "id": "prod_sensor_soil",
            "name": "Sensor de Solo IoT",
            "slug": "sensor-solo-iot",
            "description": "Sensor de humidade, temperatura e pH do solo com conectividade LoRa. Inclui 1 ano de dados na plataforma.",
            "short_description": "Sensor solo + 1 ano dados",
            "product_type": "physical",
            "category": "hardware",
            "price": 12000000,  # 120.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "track_inventory": True,
            "stock_quantity": 50,
            "sectors": ["agro"],
            "deliverables": ["Sensor", "Manual", "Acesso Plataforma 1 Ano"],
            "image_url": "/assets/img/products/sensor-soil.jpg",
            "is_active": True,
        },
        {
            "id": "prod_weather_station",
            "name": "Estação Meteorológica IoT",
            "slug": "estacao-meteo-iot",
            "description": "Estação meteorológica completa com sensores de temperatura, humidade, vento, precipitação e radiação solar.",
            "short_description": "Estação meteo completa",
            "product_type": "physical",
            "category": "hardware",
            "price": 85000000,  # 850.000 AOA
            "currency": "AOA",
            "tax_rate": 0.14,
            "track_inventory": True,
            "stock_quantity": 20,
            "sectors": ["agro", "solar", "mining"],
            "deliverables": ["Estação", "Instalação", "1 Ano Plataforma"],
            "image_url": "/assets/img/products/weather-station.jpg",
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
    
    def check_sector_mismatch(
        self,
        product_id: str,
        account_sector: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Check if product sector matches account sector.
        Returns warning info if mismatch, None if OK.
        Non-blocking: allows purchase but warns user.
        """
        if not account_sector:
            return None
        
        product = _products_store.get(product_id)
        if not product:
            return None
        
        product_sectors = product.get("sectors", [])
        if not product_sectors:
            return None
        
        # Check if account sector is in product's allowed sectors
        if account_sector in product_sectors:
            return None
        
        # Mismatch detected - return warning (non-blocking)
        product_sector_label = SECTOR_LABELS.get(product_sectors[0], product_sectors[0])
        account_sector_label = SECTOR_LABELS.get(account_sector, account_sector)
        
        return {
            "warning": True,
            "sector_mismatch": True,
            "product_sector": product_sectors[0],
            "product_sector_label": product_sector_label,
            "account_sector": account_sector,
            "account_sector_label": account_sector_label,
            "message": f"Este serviço é destinado ao sector {product_sector_label}. A sua conta está configurada para {account_sector_label}.",
            "suggestion": f"Pode continuar com a compra ou criar uma nova conta {product_sector_label}."
        }
    
    def get_cart_with_warnings(
        self,
        cart_id: str,
        account_sector: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get cart data with sector mismatch warnings for each item.
        """
        cart = self._find_cart(cart_id)
        if not cart:
            raise ValueError("Cart not found")
        
        cart_data = self._cart_to_data(cart)
        
        items_with_warnings = []
        has_warnings = False
        
        for item in cart_data.items:
            warning = self.check_sector_mismatch(item.product_id, account_sector)
            item_dict = {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "product_type": item.product_type,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "tax_amount": item.tax_amount,
                "product_image": item.product_image,
                "warning": warning,
            }
            if warning:
                has_warnings = True
            items_with_warnings.append(item_dict)
        
        return {
            "cart": {
                "id": cart_data.id,
                "user_id": cart_data.user_id,
                "item_count": cart_data.item_count,
                "subtotal": cart_data.subtotal,
                "discount_amount": cart_data.discount_amount,
                "tax_amount": cart_data.tax_amount,
                "delivery_cost": cart_data.delivery_cost,
                "total": cart_data.total,
                "currency": cart_data.currency,
            },
            "items": items_with_warnings,
            "has_sector_warnings": has_warnings,
        }


def get_sector_labels() -> Dict[str, str]:
    """Get sector labels for display."""
    return SECTOR_LABELS.copy()


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
