"""HTTP compatibility facade for sector-specific KPI responses."""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_current_account, get_current_user
from app.models import Account, User
from app.modules.analytics.kpi_catalog import (
    _now_minus,
    get_agro_kpis,
    get_construction_kpis,
    get_demining_kpis,
    get_environment_kpis,
    get_generic_kpis,
    get_infrastructure_kpis,
    get_kpis_for_sectors,
    get_mining_kpis,
    get_sector_alerts,
    get_solar_kpis,
)
from app.schemas import AlertsResponse, DashboardContext, KPIItem, KPIResponse

router = APIRouter(prefix="/kpi", tags=["kpi"])


@router.get("/summary", response_model=KPIResponse)
def kpi_summary(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get KPI summary, optionally filtered by sector."""
    account_sectors = []
    if account and account.sector_focus:
        account_sectors = [s.strip() for s in account.sector_focus.split(",") if s.strip()]

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

    critical_count = sum(1 for alert in alerts if alert.severity == "critical")
    warning_count = sum(1 for alert in alerts if alert.severity == "warning")

    return AlertsResponse(
        alerts=alerts,
        total=len(alerts),
        critical_count=critical_count,
        warning_count=warning_count,
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

    if sector and sector in account_sectors:
        kpis = get_kpis_for_sectors([sector])
    elif account_sectors:
        kpis = get_kpis_for_sectors(account_sectors)
    else:
        kpis = get_generic_kpis()

    alerts = get_sector_alerts(account_sectors if account_sectors else [])

    sector_names = {
        "agro": "Agricultura e Pecuaria",
        "environment": "Monitorizacao Ambiental",
        "mining": "Mineracao",
        "construction": "Construcao",
        "infrastructure": "Infraestruturas",
        "solar": "Energia Solar",
        "demining": "Desminagem",
    }

    sector_display = (
        ", ".join(sector_names.get(item, item) for item in account_sectors)
        if account_sectors
        else "Geral"
    )
    active_sector_display = sector_names.get(sector, sector) if sector else "todos os setores"

    critical_alerts = [alert for alert in alerts if alert.severity == "critical"]
    warning_alerts = [alert for alert in alerts if alert.severity == "warning"]

    summary_parts = [
        f"Conta: {account_name}.",
        f"Setores: {sector_display}.",
        f"A visualizar: {active_sector_display}.",
    ]

    warning_kpis = [kpi for kpi in kpis if kpi.status == "warning"]
    if warning_kpis:
        summary_parts.append(
            f"KPIs com atencao: {', '.join(kpi.label for kpi in warning_kpis)}."
        )

    summary_parts.append(f"Total de {len(kpis)} KPIs monitorizados.")

    if critical_alerts:
        summary_parts.append(
            f"ALERTAS CRITICOS: {len(critical_alerts)} - {critical_alerts[0].title}."
        )
    if warning_alerts:
        summary_parts.append(f"Avisos: {len(warning_alerts)}.")
    if not critical_alerts and not warning_alerts:
        summary_parts.append("Sem alertas criticos ou avisos.")

    return DashboardContext(
        account_name=account_name,
        sectors=account_sectors,
        active_sector=sector,
        kpis=kpis,
        alerts=alerts,
        services_count=len([kpi for kpi in kpis if "service" in kpi.id.lower()]) or 2,
        hardware_count=len(
            [
                kpi
                for kpi in kpis
                if "hardware" in kpi.id.lower() or "sensor" in kpi.id.lower()
            ]
        )
        or 3,
        summary_text=" ".join(summary_parts),
    )


@router.get("/details", response_model=KPIResponse)
def kpi_details(
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get system/platform level KPIs."""
    items: List[KPIItem] = [
        KPIItem(
            id="uptime",
            label="Disponibilidade",
            value=0,
            unit="%",
            status="ok",
            trend="stable",
            updated_at=_now_minus(30),
            description="Disponibilidade dos servicos GeoVision.",
        ),
        KPIItem(
            id="sla",
            label="SLA Atingido",
            value=0,
            unit="%",
            status="ok",
            trend="stable",
            updated_at=_now_minus(60),
            description="Percentagem de cumprimento dos SLAs acordados.",
        ),
        KPIItem(
            id="tickets",
            label="Tickets em Aberto",
            value=0,
            unit="",
            status="ok",
            trend="stable",
            updated_at=_now_minus(12),
            description="Pedidos de suporte em processamento.",
        ),
    ]
    return KPIResponse(items=items)


__all__ = [
    "get_agro_kpis",
    "get_construction_kpis",
    "get_demining_kpis",
    "get_environment_kpis",
    "get_generic_kpis",
    "get_infrastructure_kpis",
    "get_kpis_for_sectors",
    "get_mining_kpis",
    "get_sector_alerts",
    "get_solar_kpis",
    "router",
]
