"""Existing sector KPI catalogue exposed independently of HTTP routers."""

from typing import List

from app.schemas import AlertItem, KPIItem
from app.sector_taxonomy import normalize_public_sector


def _now_minus(minutes: int) -> None:
    """Keep the legacy call shape while marking placeholder timestamps as absent."""

    del minutes
    return None


def get_agro_kpis() -> List[KPIItem]:
    return [
        KPIItem(
            id="soil_moisture",
            label="Humidade do Solo",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(30),
            sector="agriculture",
            description="Ultima leitura de humidade do solo no local selecionado.",
        ),
        KPIItem(
            id="water_level",
            label="Disponibilidade de Agua",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(30),
            sector="agriculture",
            description="Nivel ou disponibilidade de agua medida no local.",
        ),
        KPIItem(
            id="data_completeness",
            label="Completude dos Dados",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector="agriculture",
            description="Percentagem das leituras esperadas que foram recebidas.",
        ),
        KPIItem(
            id="open_incidents",
            label="Incidentes Abertos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="agriculture",
            description="Alertas operacionais ainda nao resolvidos.",
        ),
    ]


def get_mining_kpis() -> List[KPIItem]:
    """Expose the mining KPI shape without inventing source measurements."""

    return [
        KPIItem(
            id="extraction_volume",
            label="Volume Extraido",
            value="—",
            unit="m3",
            status=None,
            trend=None,
            updated_at=_now_minus(60),
            sector="mining",
            description="Volume total de material extraido no periodo atual.",
        ),
        KPIItem(
            id="slope_stability",
            label="Estabilidade Taludes",
            value="—",
            unit="%",
            status=None,
            trend=None,
            updated_at=_now_minus(15),
            sector="mining",
            description="Indice de estabilidade dos taludes principais. Valores acima de 90% sao seguros.",
        ),
        KPIItem(
            id="sensors_active",
            label="Sensores Ativos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="mining",
            description="Numero de sensores geotecnicos a transmitir dados em tempo real.",
        ),
        KPIItem(
            id="geotechnical_alerts",
            label="Alertas Geotecnicos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector="mining",
            description="Alertas ativos relacionados com movimentacao de terreno ou instabilidade.",
        ),
    ]


def get_construction_kpis() -> List[KPIItem]:
    return get_infrastructure_kpis()

    return [
        KPIItem(
            id="progress_percent",
            label="Progresso Obra",
            value=0,
            unit="%",
            status="ok",
            trend="stable",
            updated_at=_now_minus(120),
            sector="construction_infrastructure",
            description="Percentagem de conclusao da obra principal baseada em levantamentos topograficos.",
        ),
        KPIItem(
            id="conformity_index",
            label="Conformidade Projeto",
            value=0,
            unit="%",
            status="ok",
            trend="stable",
            updated_at=_now_minus(180),
            sector="construction_infrastructure",
            description="Indice de conformidade entre o executado e o projeto original.",
        ),
        KPIItem(
            id="pending_inspections",
            label="Inspecoes Pendentes",
            value=0,
            unit="",
            status="ok",
            trend="stable",
            updated_at=_now_minus(60),
            sector="construction_infrastructure",
            description="Numero de inspecoes de drone agendadas mas ainda nao realizadas.",
        ),
        KPIItem(
            id="volume_earthwork",
            label="Volume Terraplanagem",
            value=0,
            unit="m3",
            status="ok",
            trend="stable",
            updated_at=_now_minus(240),
            sector="construction_infrastructure",
            description="Volume de terraplanagem executado medido por fotogrametria.",
        ),
    ]


def get_infrastructure_kpis() -> List[KPIItem]:
    return [
        KPIItem(
            id="data_freshness",
            label="Dados Recentes",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="construction_infrastructure",
            description="Percentagem de dispositivos com dados recentes.",
        ),
        KPIItem(
            id="device_health",
            label="Saude dos Dispositivos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="construction_infrastructure",
            description="Dispositivos online, com bateria e sinal adequados.",
        ),
        KPIItem(
            id="maintenance_due",
            label="Manutencao Pendente",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(15),
            sector="construction_infrastructure",
            description="Equipamentos com manutencao ou intervencao pendente.",
        ),
        KPIItem(
            id="open_incidents",
            label="Incidentes Abertos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="construction_infrastructure",
            description="Alertas operacionais ainda nao resolvidos.",
        ),
    ]


def get_environment_kpis() -> List[KPIItem]:
    return [
        KPIItem(
            id="air_quality",
            label="Qualidade do Ar",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector="environment",
            description="Ultima leitura dos canais de qualidade do ar configurados.",
        ),
        KPIItem(
            id="water_level",
            label="Nivel de Agua",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector="environment",
            description="Nivel atual do deposito ou ponto de agua monitorizado.",
        ),
        KPIItem(
            id="leak_events",
            label="Eventos de Fuga",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="environment",
            description="Fugas detetadas que requerem verificacao.",
        ),
        KPIItem(
            id="data_completeness",
            label="Completude dos Dados",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector="environment",
            description="Percentagem das leituras esperadas que foram recebidas.",
        ),
    ]


def get_solar_kpis() -> List[KPIItem]:
    return get_industry_energy_utilities_kpis()

    return [
        KPIItem(
            id="panel_efficiency",
            label="Eficiencia Paineis",
            value=0,
            unit="%",
            status="ok",
            trend="stable",
            updated_at=_now_minus(30),
            sector="industry_energy_utilities",
            description="Eficiencia media dos paineis solares baseada em inspecao termica.",
        ),
        KPIItem(
            id="irradiance_avg",
            label="Irradiancia Media",
            value=0,
            unit="kWh/m2",
            status="ok",
            trend="stable",
            updated_at=_now_minus(15),
            sector="industry_energy_utilities",
            description="Irradiancia solar media diaria medida pelos sensores.",
        ),
        KPIItem(
            id="anomaly_panels",
            label="Paineis com Anomalia",
            value=0,
            unit="",
            status="ok",
            trend="stable",
            updated_at=_now_minus(60),
            sector="industry_energy_utilities",
            description="Paineis identificados com hotspots ou anomalias termicas.",
        ),
        KPIItem(
            id="energy_generated",
            label="Energia Gerada",
            value=0,
            unit="MWh",
            status="ok",
            trend="stable",
            updated_at=_now_minus(120),
            sector="industry_energy_utilities",
            description="Energia total gerada no mes atual.",
        ),
    ]


def get_demining_kpis() -> List[KPIItem]:
    return get_infrastructure_kpis()

    return [
        KPIItem(
            id="area_cleared",
            label="Area Verificada",
            value=0,
            unit="m2",
            status="ok",
            trend="stable",
            updated_at=_now_minus(60),
            sector="demining",
            description="Area total verificada e declarada segura.",
        ),
        KPIItem(
            id="objects_detected",
            label="Objetos Detectados",
            value=0,
            unit="",
            status="ok",
            trend="stable",
            updated_at=_now_minus(30),
            sector="demining",
            description="Total de objetos metalicos detectados que requerem verificacao manual.",
        ),
        KPIItem(
            id="progress_rate",
            label="Taxa de Progresso",
            value=0,
            unit="m2/dia",
            status="ok",
            trend="stable",
            updated_at=_now_minus(120),
            sector="demining",
            description="Taxa media de area verificada por dia de operacao.",
        ),
        KPIItem(
            id="priority_zones",
            label="Zonas Prioritarias",
            value=0,
            unit="",
            status="ok",
            trend="stable",
            updated_at=_now_minus(180),
            sector="demining",
            description="Numero de zonas identificadas como alta prioridade para verificacao.",
        ),
    ]


def get_industry_energy_utilities_kpis() -> List[KPIItem]:
    """Safe operational indicators until specialist sector evidence is connected."""

    return [
        KPIItem(
            id="data_freshness",
            label="Atualidade dos Dados",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="industry_energy_utilities",
            description="Atualidade das fontes configuradas para os ativos monitorizados.",
        ),
        KPIItem(
            id="asset_health",
            label="Estado dos Ativos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="industry_energy_utilities",
            description="Estado observado dos ativos com uma fonte validada.",
        ),
        KPIItem(
            id="maintenance_due",
            label="Manutenção Pendente",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(15),
            sector="industry_energy_utilities",
            description="Intervenções de manutenção registadas e ainda pendentes.",
        ),
        KPIItem(
            id="open_incidents",
            label="Incidentes Abertos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="industry_energy_utilities",
            description="Ocorrências operacionais abertas que requerem acompanhamento.",
        ),
    ]


def get_ports_logistics_kpis() -> List[KPIItem]:
    """Safe logistics indicators derived only after their sources are connected."""

    return [
        KPIItem(
            id="tracking_coverage",
            label="Cobertura de Tracking",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="ports_logistics",
            description="Ativos elegíveis com uma posição recente e fonte validada.",
        ),
        KPIItem(
            id="data_completeness",
            label="Completude dos Dados",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector="ports_logistics",
            description="Percentagem das observações esperadas que foram recebidas.",
        ),
        KPIItem(
            id="open_incidents",
            label="Ocorrências Abertas",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector="ports_logistics",
            description="Ocorrências abertas em pátios, terminais, corredores ou ativos.",
        ),
        KPIItem(
            id="maintenance_due",
            label="Manutenção Pendente",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(15),
            sector="ports_logistics",
            description="Ativos com manutenção ou inspeção registada como pendente.",
        ),
    ]


def get_generic_kpis() -> List[KPIItem]:
    """Expose an unconfigured dashboard shape without synthetic healthy values."""

    return [
        KPIItem(
            id="services_active",
            label="Servicos Ativos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(10),
            sector=None,
            description="Numero de servicos GeoVision atualmente em execucao.",
        ),
        KPIItem(
            id="hardware_active",
            label="Hardware Instalado",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(5),
            sector=None,
            description="Equipamentos IoT e sensores instalados e operacionais.",
        ),
        KPIItem(
            id="reports_ready",
            label="Relatorios Disponiveis",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(15),
            sector=None,
            description="Relatorios prontos para download ou visualizacao.",
        ),
        KPIItem(
            id="alerts_open",
            label="Alertas Abertos",
            value="—",
            unit="",
            status=None,
            trend=None,
            updated_at=_now_minus(2),
            sector=None,
            description="Alertas ativos que podem requerer atencao.",
        ),
    ]


SECTOR_KPI_FUNCTIONS = {
    "agriculture": get_agro_kpis,
    "environment": get_environment_kpis,
    "mining": get_mining_kpis,
    "construction_infrastructure": get_infrastructure_kpis,
    "industry_energy_utilities": get_industry_energy_utilities_kpis,
    "ports_logistics": get_ports_logistics_kpis,
}


def get_kpis_for_sectors(sectors: List[str]) -> List[KPIItem]:
    """Get the existing KPI definitions for the requested sector identifiers."""

    kpis = []
    normalized_sectors = list(
        dict.fromkeys(normalize_public_sector(item) for item in sectors)
    )
    for sector in normalized_sectors:
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
    "get_industry_energy_utilities_kpis",
    "get_infrastructure_kpis",
    "get_kpis_for_sectors",
    "get_mining_kpis",
    "get_ports_logistics_kpis",
    "get_sector_alerts",
    "get_solar_kpis",
]
