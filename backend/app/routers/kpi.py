"""
KPI Router - Sector-specific Key Performance Indicators

Each sector has relevant KPIs that make sense for that industry.
KPIs include descriptions to help the chatbot explain them to users.
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_account, get_current_user
from app.schemas import KPIItem, KPIResponse, AlertItem, AlertsResponse, DashboardContext
from app.models import Account, User

router = APIRouter(prefix="/kpi", tags=["kpi"])


def _now_minus(minutes: int) -> datetime:
    return datetime.utcnow() - timedelta(minutes=minutes)


# ============================================================================
# SECTOR-SPECIFIC KPI DEFINITIONS
# Each sector has relevant KPIs that make sense for that industry
# ============================================================================

def get_agro_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="ndvi_avg", label="NDVI Medio", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(30), sector="agro",
                description="Indice de vegetacao medio das areas monitoradas. Valores acima de 0.6 indicam vegetacao saudavel."),
        KPIItem(id="water_stress", label="Stress Hidrico", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(45), sector="agro",
                description="Percentagem da area com indicadores de stress hidrico. Abaixo de 20% e considerado normal."),
        KPIItem(id="hectares_monitored", label="Hectares Monitorados", value=0, unit="ha", status="ok", trend="stable",
                updated_at=_now_minus(60), sector="agro",
                description="Total de area agricola sob monitorizacao ativa por drone e sensores."),
        KPIItem(id="yield_estimate", label="Produtividade Estimada", value=0, unit="ton/ha", status="ok", trend="stable",
                updated_at=_now_minus(120), sector="agro",
                description="Estimativa de produtividade baseada em analise multispectral e historico."),
    ]


def get_mining_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="extraction_volume", label="Volume Extraido", value=0, unit="m3", status="ok", trend="stable",
                updated_at=_now_minus(60), sector="mining",
                description="Volume total de material extraido no periodo atual."),
        KPIItem(id="slope_stability", label="Estabilidade Taludes", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(15), sector="mining",
                description="Indice de estabilidade dos taludes principais. Valores acima de 90% sao seguros."),
        KPIItem(id="sensors_active", label="Sensores Ativos", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(5), sector="mining",
                description="Numero de sensores geotecnicos a transmitir dados em tempo real."),
        KPIItem(id="geotechnical_alerts", label="Alertas Geotecnicos", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(10), sector="mining",
                description="Alertas ativos relacionados com movimentacao de terreno ou instabilidade."),
    ]


def get_construction_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="progress_percent", label="Progresso Obra", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(120), sector="construction",
                description="Percentagem de conclusao da obra principal baseada em levantamentos topograficos."),
        KPIItem(id="conformity_index", label="Conformidade Projeto", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(180), sector="construction",
                description="Indice de conformidade entre o executado e o projeto original."),
        KPIItem(id="pending_inspections", label="Inspecoes Pendentes", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(60), sector="construction",
                description="Numero de inspecoes de drone agendadas mas ainda nao realizadas."),
        KPIItem(id="volume_earthwork", label="Volume Terraplanagem", value=0, unit="m3", status="ok", trend="stable",
                updated_at=_now_minus(240), sector="construction",
                description="Volume de terraplanagem executado medido por fotogrametria."),
    ]


def get_infrastructure_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="km_monitored", label="Km Monitorados", value=0, unit="km", status="ok", trend="stable",
                updated_at=_now_minus(60), sector="infrastructure",
                description="Extensao total de infraestrutura linear (estradas, linhas) sob monitorizacao."),
        KPIItem(id="structural_integrity", label="Integridade Estrutural", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(30), sector="infrastructure",
                description="Indice medio de integridade das estruturas inspecionadas (pontes, viadutos)."),
        KPIItem(id="vibration_sensors", label="Sensores Vibracao", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(5), sector="infrastructure",
                description="Sensores de vibracao ativos em pontes e estruturas criticas."),
        KPIItem(id="maintenance_alerts", label="Alertas Manutencao", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(15), sector="infrastructure",
                description="Alertas ativos que requerem intervencao de manutencao."),
    ]


def get_solar_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="panel_efficiency", label="Eficiencia Paineis", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(30), sector="solar",
                description="Eficiencia media dos paineis solares baseada em inspecao termica."),
        KPIItem(id="irradiance_avg", label="Irradiancia Media", value=0, unit="kWh/m2", status="ok", trend="stable",
                updated_at=_now_minus(15), sector="solar",
                description="Irradiancia solar media diaria medida pelos sensores."),
        KPIItem(id="anomaly_panels", label="Paineis com Anomalia", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(60), sector="solar",
                description="Paineis identificados com hotspots ou anomalias termicas."),
        KPIItem(id="energy_generated", label="Energia Gerada", value=0, unit="MWh", status="ok", trend="stable",
                updated_at=_now_minus(120), sector="solar",
                description="Energia total gerada no mes atual."),
    ]


def get_demining_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="area_cleared", label="Area Verificada", value=0, unit="m2", status="ok", trend="stable",
                updated_at=_now_minus(60), sector="demining",
                description="Area total verificada e declarada segura."),
        KPIItem(id="objects_detected", label="Objetos Detectados", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(30), sector="demining",
                description="Total de objetos metalicos detectados que requerem verificacao manual."),
        KPIItem(id="progress_rate", label="Taxa de Progresso", value=0, unit="m2/dia", status="ok", trend="stable",
                updated_at=_now_minus(120), sector="demining",
                description="Taxa media de area verificada por dia de operacao."),
        KPIItem(id="priority_zones", label="Zonas Prioritarias", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(180), sector="demining",
                description="Numero de zonas identificadas como alta prioridade para verificacao."),
    ]


def get_generic_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="services_active", label="Servicos Ativos", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(10), sector="generic",
                description="Numero de servicos GeoVision atualmente em execucao."),
        KPIItem(id="hardware_active", label="Hardware Instalado", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(5), sector="generic",
                description="Equipamentos IoT e sensores instalados e operacionais."),
        KPIItem(id="reports_ready", label="Relatorios Disponiveis", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(15), sector="generic",
                description="Relatorios prontos para download ou visualizacao."),
        KPIItem(id="alerts_open", label="Alertas Abertos", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(2), sector="generic",
                description="Alertas ativos que podem requerer atencao."),
    ]


SECTOR_KPI_FUNCTIONS = {
    "agro": get_agro_kpis,
    "mining": get_mining_kpis,
    "construction": get_construction_kpis,
    "infrastructure": get_infrastructure_kpis,
    "solar": get_solar_kpis,
    "demining": get_demining_kpis,
}


def get_kpis_for_sectors(sectors: List[str]) -> List[KPIItem]:
    """Get KPIs for given sectors."""
    kpis = []
    for sector in sectors:
        if sector in SECTOR_KPI_FUNCTIONS:
            kpis.extend(SECTOR_KPI_FUNCTIONS[sector]())
    if not kpis:
        kpis = get_generic_kpis()
    return kpis


# ============================================================================
# ALERTS - Demo data per sector
# ============================================================================

def get_sector_alerts(sectors: List[str]) -> List[AlertItem]:
    """Get alerts for sectors. Returns empty list when no real data is available."""
    # When real alerting is integrated, this will query the alerts database.
    return []


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/summary", response_model=KPIResponse)
def kpi_summary(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get KPI summary, optionally filtered by sector."""
    # Parse account sectors
    account_sectors = []
    if account and account.sector_focus:
        account_sectors = [s.strip() for s in account.sector_focus.split(",") if s.strip()]
    
    # Filter by requested sector if provided
    if sector and sector in account_sectors:
        items = get_kpis_for_sectors([sector])
    elif account_sectors:
        items = get_kpis_for_sectors(account_sectors)
    else:
        items = get_generic_kpis()
    
    return KPIResponse(items=items, sector=sector)


@router.get("/alerts", response_model=AlertsResponse)
def kpi_alerts(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get alerts, optionally filtered by sector."""
    account_sectors = []
    if account and account.sector_focus:
        account_sectors = [s.strip() for s in account.sector_focus.split(",") if s.strip()]
    
    if sector and sector in account_sectors:
        sectors_to_query = [sector]
    elif account_sectors:
        sectors_to_query = account_sectors
    else:
        sectors_to_query = []
    
    alerts = get_sector_alerts(sectors_to_query)
    
    critical_count = sum(1 for a in alerts if a.severity == "critical")
    warning_count = sum(1 for a in alerts if a.severity == "warning")
    
    return AlertsResponse(
        alerts=alerts,
        total=len(alerts),
        critical_count=critical_count,
        warning_count=warning_count
    )


@router.get("/context", response_model=DashboardContext)
def dashboard_context(
    sector: Optional[str] = Query(None, description="Active sector filter"),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """
    Get structured dashboard context for chatbot integration.
    
    This endpoint provides all visible data in a format the chatbot can understand
    to give accurate assistance based on what the user is seeing.
    """
    account_name = account.name if account else "Conta GeoVision"
    account_sectors = []
    if account and account.sector_focus:
        account_sectors = [s.strip() for s in account.sector_focus.split(",") if s.strip()]
    
    # Get KPIs
    if sector and sector in account_sectors:
        kpis = get_kpis_for_sectors([sector])
    elif account_sectors:
        kpis = get_kpis_for_sectors(account_sectors)
    else:
        kpis = get_generic_kpis()
    
    # Get alerts
    alerts = get_sector_alerts(account_sectors if account_sectors else [])
    
    # Build human-readable summary for chatbot
    sector_names = {
        "agro": "Agricultura e Pecuaria",
        "mining": "Mineracao",
        "construction": "Construcao",
        "infrastructure": "Infraestruturas",
        "solar": "Energia Solar",
        "demining": "Desminagem",
    }
    
    sector_display = ", ".join(sector_names.get(s, s) for s in account_sectors) if account_sectors else "Geral"
    active_sector_display = sector_names.get(sector, sector) if sector else "todos os setores"
    
    critical_alerts = [a for a in alerts if a.severity == "critical"]
    warning_alerts = [a for a in alerts if a.severity == "warning"]
    
    summary_parts = [
        f"Conta: {account_name}.",
        f"Setores: {sector_display}.",
        f"A visualizar: {active_sector_display}.",
    ]
    
    # Add KPI highlights
    warning_kpis = [k for k in kpis if k.status == "warning"]
    ok_kpis = [k for k in kpis if k.status == "ok"]
    
    if warning_kpis:
        summary_parts.append(f"KPIs com atencao: {', '.join(k.label for k in warning_kpis)}.")
    
    summary_parts.append(f"Total de {len(kpis)} KPIs monitorizados.")
    
    # Add alert summary
    if critical_alerts:
        summary_parts.append(f"ALERTAS CRITICOS: {len(critical_alerts)} - {critical_alerts[0].title}.")
    if warning_alerts:
        summary_parts.append(f"Avisos: {len(warning_alerts)}.")
    if not critical_alerts and not warning_alerts:
        summary_parts.append("Sem alertas criticos ou avisos.")
    
    summary_text = " ".join(summary_parts)
    
    return DashboardContext(
        account_name=account_name,
        sectors=account_sectors,
        active_sector=sector,
        kpis=kpis,
        alerts=alerts,
        services_count=len([k for k in kpis if "service" in k.id.lower()]) or 2,
        hardware_count=len([k for k in kpis if "hardware" in k.id.lower() or "sensor" in k.id.lower()]) or 3,
        summary_text=summary_text,
    )


@router.get("/details", response_model=KPIResponse)
def kpi_details(
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get system/platform level KPIs."""
    items: List[KPIItem] = [
        KPIItem(id="uptime", label="Disponibilidade", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(30), description="Disponibilidade dos servicos GeoVision."),
        KPIItem(id="sla", label="SLA Atingido", value=0, unit="%", status="ok", trend="stable",
                updated_at=_now_minus(60), description="Percentagem de cumprimento dos SLAs acordados."),
        KPIItem(id="tickets", label="Tickets em Aberto", value=0, unit="", status="ok", trend="stable",
                updated_at=_now_minus(12), description="Pedidos de suporte em processamento."),
    ]
    return KPIResponse(items=items)
