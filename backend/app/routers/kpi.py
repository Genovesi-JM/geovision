"""HTTP compatibility facade for sector-specific KPI responses."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

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
from app.sector_taxonomy import (
    PUBLIC_SECTORS,
    PUBLIC_SECTORS_BY_ID,
    normalize_public_sector,
    normalize_sector_focus,
)

router = APIRouter(prefix="/kpi", tags=["kpi"])


def _account_sectors(account: Account | None) -> list[str]:
    return [
        item
        for item in normalize_sector_focus(
            account.sector_focus if account else ""
        ).split(",")
        if item in PUBLIC_SECTORS
    ]


def _authorized_sector_filter(
    sector: str | None,
    account_sectors: list[str],
) -> str | None:
    if sector is None:
        return None
    requested_sector = normalize_public_sector(sector)
    if requested_sector not in PUBLIC_SECTORS:
        raise HTTPException(status_code=422, detail="Unsupported sector filter")
    if requested_sector not in account_sectors:
        raise HTTPException(
            status_code=403, detail="Sector is not enabled for this account"
        )
    return requested_sector


@router.get("/summary", response_model=KPIResponse)
def kpi_summary(
    sector: Optional[str] = Query(None, max_length=80, description="Filter by sector"),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get KPI summary, optionally filtered by sector."""
    account_sectors = _account_sectors(account)
    requested_sector = _authorized_sector_filter(sector, account_sectors)

    if requested_sector and requested_sector in account_sectors:
        items = get_kpis_for_sectors([requested_sector])
    elif account_sectors:
        items = get_kpis_for_sectors(account_sectors)
    else:
        items = get_generic_kpis()

    return KPIResponse(items=items, sector=requested_sector)


@router.get("/alerts", response_model=AlertsResponse)
def kpi_alerts(
    sector: Optional[str] = Query(None, max_length=80, description="Filter by sector"),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """Get alerts, optionally filtered by sector."""
    account_sectors = _account_sectors(account)
    requested_sector = _authorized_sector_filter(sector, account_sectors)

    if requested_sector and requested_sector in account_sectors:
        sectors_to_query = [requested_sector]
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
        availability="NO_DATA",
    )


@router.get("/context", response_model=DashboardContext)
def dashboard_context(
    sector: Optional[str] = Query(
        None, max_length=80, description="Active sector filter"
    ),
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    """
    Get structured dashboard context for chatbot integration.

    This endpoint provides all visible data in a format the chatbot can understand
    to give accurate assistance based on what the user is seeing.
    """
    account_name = account.name if account else "Conta GeoVision"
    account_sectors = _account_sectors(account)
    requested_sector = _authorized_sector_filter(sector, account_sectors)

    if requested_sector and requested_sector in account_sectors:
        kpis = get_kpis_for_sectors([requested_sector])
    elif account_sectors:
        kpis = get_kpis_for_sectors(account_sectors)
    else:
        kpis = get_generic_kpis()

    alerts = get_sector_alerts(account_sectors if account_sectors else [])

    sector_names = {key: item.label_pt for key, item in PUBLIC_SECTORS_BY_ID.items()}

    sector_display = (
        ", ".join(sector_names.get(item, item) for item in account_sectors)
        if account_sectors
        else "Geral"
    )
    active_sector_display = (
        sector_names.get(requested_sector, requested_sector)
        if requested_sector
        else "todos os setores"
    )

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
        summary_parts.append("Alertas: sem fonte de dados ligada.")

    return DashboardContext(
        account_name=account_name,
        sectors=account_sectors,
        active_sector=requested_sector,
        kpis=kpis,
        alerts=alerts,
        alerts_availability="NO_DATA",
        services_count=None,
        hardware_count=None,
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
            value="—",
            unit="%",
            status=None,
            trend=None,
            updated_at=_now_minus(30),
            description="Disponibilidade dos servicos GeoVision.",
        ),
        KPIItem(
            id="sla",
            label="SLA Atingido",
            value="—",
            unit="%",
            status=None,
            trend=None,
            updated_at=_now_minus(60),
            description="Percentagem de cumprimento dos SLAs acordados.",
        ),
        KPIItem(
            id="tickets",
            label="Tickets em Aberto",
            value="—",
            unit="",
            status=None,
            trend=None,
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
