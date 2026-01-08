from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends

from app.deps import get_current_account, get_current_user
from app.schemas import KPIItem, KPIResponse
from app.models import Account, User

router = APIRouter(prefix="/kpi", tags=["kpi"])


def _now_minus(minutes: int) -> datetime:
    return datetime.utcnow() - timedelta(minutes=minutes)


@router.get("/summary", response_model=KPIResponse)
def kpi_summary(
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    items: List[KPIItem] = [
        KPIItem(id="services_active", label="ServiA§os ativos", value=4, unit="", status="ok", trend="up", updated_at=_now_minus(10)),
        KPIItem(id="hardware_active", label="Hardware instalado", value=6, unit="", status="ok", trend="stable", updated_at=_now_minus(5)),
        KPIItem(id="reports_ready", label="RelatA³rios disponA­veis", value=3, unit="", status="ok", trend="up", updated_at=_now_minus(15)),
        KPIItem(id="alerts_open", label="Alertas de campo", value=1, unit="", status="watch", trend="down", updated_at=_now_minus(2)),
    ]
    return KPIResponse(items=items)


@router.get("/details", response_model=KPIResponse)
def kpi_details(
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    items: List[KPIItem] = [
        KPIItem(id="uptime", label="Disponibilidade", value=99.4, unit="%", status="ok", trend="up", updated_at=_now_minus(30)),
        KPIItem(id="sla", label="SLA atingido", value=97.0, unit="%", status="ok", trend="stable", updated_at=_now_minus(60)),
        KPIItem(id="tickets", label="Tickets em aberto", value=2, unit="", status="watch", trend="up", updated_at=_now_minus(12)),
    ]
    return KPIResponse(items=items)


@router.get("/map_layers", response_model=KPIResponse)
def kpi_map_layers(
    user: User = Depends(get_current_user),
    account: Account = Depends(get_current_account),
):
    items: List[KPIItem] = [
        KPIItem(id="fields_monitored", label="Áreas monitoradas", value=12, unit="", status="ok", trend="up", updated_at=_now_minus(45)),
        KPIItem(id="drones_active", label="Drones ativos", value=3, unit="", status="ok", trend="stable", updated_at=_now_minus(5)),
        KPIItem(id="zones_alert", label="Zonas em alerta", value=1, unit="", status="watch", trend="up", updated_at=_now_minus(8)),
    ]
    return KPIResponse(items=items)
