"""Existing sector KPI catalogue exposed independently of HTTP routers."""

from datetime import datetime, timedelta
from typing import List

from app.core.time import utc_now
from app.schemas import AlertItem, KPIItem


def _now_minus(minutes: int) -> datetime:
    return utc_now() - timedelta(minutes=minutes)


def get_agro_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="soil_moisture", label="Humidade do Solo", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(30), sector="agro", description="Ultima leitura de humidade do solo no local selecionado."),
        KPIItem(id="water_level", label="Disponibilidade de Agua", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(30), sector="agro", description="Nivel ou disponibilidade de agua medida no local."),
        KPIItem(id="data_completeness", label="Completude dos Dados", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(10), sector="agro", description="Percentagem das leituras esperadas que foram recebidas."),
        KPIItem(id="open_incidents", label="Incidentes Abertos", value=0, unit="", status=None, trend=None,
                updated_at=_now_minus(5), sector="agro", description="Alertas operacionais ainda nao resolvidos."),
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
        KPIItem(id="data_freshness", label="Dados Recentes", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(5), sector="infrastructure", description="Percentagem de dispositivos com dados recentes."),
        KPIItem(id="device_health", label="Saude dos Dispositivos", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(5), sector="infrastructure", description="Dispositivos online, com bateria e sinal adequados."),
        KPIItem(id="maintenance_due", label="Manutencao Pendente", value=0, unit="", status=None, trend=None,
                updated_at=_now_minus(15), sector="infrastructure", description="Equipamentos com manutencao ou intervencao pendente."),
        KPIItem(id="open_incidents", label="Incidentes Abertos", value=0, unit="", status=None, trend=None,
                updated_at=_now_minus(5), sector="infrastructure", description="Alertas operacionais ainda nao resolvidos."),
    ]


def get_environment_kpis() -> List[KPIItem]:
    return [
        KPIItem(id="air_quality", label="Qualidade do Ar", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(10), sector="environment", description="Ultima leitura dos canais de qualidade do ar configurados."),
        KPIItem(id="water_level", label="Nivel de Agua", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(10), sector="environment", description="Nivel atual do deposito ou ponto de agua monitorizado."),
        KPIItem(id="leak_events", label="Eventos de Fuga", value=0, unit="", status=None, trend=None,
                updated_at=_now_minus(5), sector="environment", description="Fugas detetadas que requerem verificacao."),
        KPIItem(id="data_completeness", label="Completude dos Dados", value="—", unit="", status=None, trend=None,
                updated_at=_now_minus(10), sector="environment", description="Percentagem das leituras esperadas que foram recebidas."),
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
    "environment": get_environment_kpis,
    "mining": get_mining_kpis,
    "construction": get_construction_kpis,
    "infrastructure": get_infrastructure_kpis,
    "solar": get_solar_kpis,
    "demining": get_demining_kpis,
}


def get_kpis_for_sectors(sectors: List[str]) -> List[KPIItem]:
    """Get the existing KPI definitions for the requested sector identifiers."""

    kpis = []
    for sector in sectors:
        if sector in SECTOR_KPI_FUNCTIONS:
            kpis.extend(SECTOR_KPI_FUNCTIONS[sector]())
    if not kpis:
        kpis = get_generic_kpis()
    return kpis


def get_sector_alerts(sectors: List[str]) -> List[AlertItem]:
    """Return no synthetic alerts until a real alert source is connected."""

    del sectors
    return []


__all__ = [
    "SECTOR_KPI_FUNCTIONS",
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
]
