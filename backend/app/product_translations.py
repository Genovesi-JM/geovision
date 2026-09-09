"""Localized public copy for products currently advertised by GeoVision."""

from __future__ import annotations
from typing import Any


def _copy(pt_name: str, pt_desc: str, en_name: str, en_desc: str,
          es_name: str, es_desc: str, fr_name: str, fr_desc: str) -> dict[str, dict[str, str]]:
    return {
        "pt": {"name": pt_name, "description": pt_desc, "short_description": pt_desc},
        "en": {"name": en_name, "description": en_desc, "short_description": en_desc},
        "es": {"name": es_name, "description": es_desc, "short_description": es_desc},
        "fr": {"name": fr_name, "description": fr_desc, "short_description": fr_desc},
    }


PUBLIC_PRODUCT_TRANSLATIONS = {
    "prod_infra_progress": _copy(
        "Monitorização de Progresso de Obra", "Acompanhamento visual e volumétrico do progresso da construção, com evidências periódicas.",
        "Construction Progress Monitoring", "Visual and volumetric construction progress tracking with periodic evidence.",
        "Seguimiento del Progreso de Obra", "Seguimiento visual y volumétrico del progreso de la obra con evidencias periódicas.",
        "Suivi de l’Avancement des Travaux", "Suivi visuel et volumétrique du chantier avec des preuves périodiques."),
    "prod_infra_inspection": _copy(
        "Inspeção Visual de Estruturas", "Inspeção visual detalhada de pontes, torres e edifícios, com evidências anotadas para revisão técnica.",
        "Visual Structure Inspection", "Detailed visual inspection of bridges, towers and buildings with annotated evidence for technical review.",
        "Inspección Visual de Estructuras", "Inspección visual detallada de puentes, torres y edificios con evidencias anotadas para revisión técnica.",
        "Inspection Visuelle des Structures", "Inspection visuelle détaillée de ponts, tours et bâtiments avec preuves annotées pour examen technique."),
    "prod_aerial_basic_mapping": _copy(
        "Mapeamento Aéreo Essencial", "Mapeamento visual de uma exploração, propriedade ou local com ortomosaico e resumo de observações.",
        "Essential Aerial Mapping", "Visual mapping of a farm, property or site with an orthomosaic and observation summary.",
        "Cartografía Aérea Esencial", "Cartografía visual de una explotación, propiedad o sitio con ortomosaico y resumen de observaciones.",
        "Cartographie Aérienne Essentielle", "Cartographie visuelle d’une exploitation, propriété ou site avec orthomosaïque et synthèse des observations."),
    "prod_agro_visual_inspection": _copy(
        "Inspeção Visual Agrícola", "Inspeção aérea para documentar culturas, irrigação, acessos e anomalias visíveis sem prometer análise multiespectral.",
        "Visual Farm Inspection", "Aerial inspection documenting crops, irrigation, access and visible anomalies without claiming multispectral analysis.",
        "Inspección Visual Agrícola", "Inspección aérea para documentar cultivos, riego, accesos y anomalías visibles sin prometer análisis multiespectral.",
        "Inspection Visuelle Agricole", "Inspection aérienne des cultures, de l’irrigation, des accès et anomalies visibles, sans promesse d’analyse multispectrale."),
    "prod_supply_soil_probe": _copy(
        "Kit de Sondas de Solo", "Sondas de humidade para substituição, expansão ou primeiro protótipo GeoVision, sujeitas a verificação de compatibilidade.",
        "Soil Probe Kit", "Moisture probes for replacement, expansion or a first GeoVision prototype, subject to compatibility checks.",
        "Kit de Sondas de Suelo", "Sondas de humedad para sustitución, ampliación o primer prototipo GeoVision, sujetas a verificación de compatibilidad.",
        "Kit de Sondes de Sol", "Sondes d’humidité pour remplacement, extension ou premier prototype GeoVision, sous réserve de compatibilité."),
    "prod_supply_irrigation_parts": _copy(
        "Kit de Componentes de Irrigação", "Válvula de baixa tensão, sensor de caudal e ligações para um protótipo de irrigação monitorizada.",
        "Irrigation Components Kit", "Low-voltage valve, flow sensor and fittings for a monitored irrigation prototype.",
        "Kit de Componentes de Riego", "Válvula de baja tensión, sensor de caudal y conexiones para un prototipo de riego monitorizado.",
        "Kit de Composants d’Irrigation", "Vanne basse tension, capteur de débit et raccords pour un prototype d’irrigation surveillée."),
    "prod_supply_monitoring_spares": _copy(
        "Pack de Acessórios para Sensores", "Cabos, conectores e pequenos consumíveis para instalar e manter um nó GeoVision.",
        "Sensor Accessories Pack", "Cables, connectors and small consumables for installing and maintaining a GeoVision node.",
        "Pack de Accesorios para Sensores", "Cables, conectores y pequeños consumibles para instalar y mantener un nodo GeoVision.",
        "Pack d’Accessoires pour Capteurs", "Câbles, connecteurs et petits consommables pour installer et entretenir un nœud GeoVision."),
    "prod_supply_weather_pack": _copy(
        "Pack de Sensores Meteorológicos", "Sensores de temperatura, humidade e chuva para protótipos de campo e pequenas estações meteorológicas.",
        "Weather Sensor Pack", "Temperature, humidity and rain sensors for field prototypes and small weather stations.",
        "Pack de Sensores Meteorológicos", "Sensores de temperatura, humedad y lluvia para prototipos de campo y pequeñas estaciones meteorológicas.",
        "Pack de Capteurs Météo", "Capteurs de température, d’humidité et de pluie pour prototypes de terrain et petites stations météo."),
    "prod_kit_water_tank_starter": _copy(
        "GV Level — Água e Bomba", "Acompanhe nível do depósito, caudal e funcionamento da bomba com alertas configuráveis.",
        "GV Level — Water & Pump", "Track tank level, flow and pump operation with configurable alerts.",
        "GV Level — Agua y Bomba", "Supervisa el nivel del depósito, el caudal y el funcionamiento de la bomba con alertas configurables.",
        "GV Level — Eau et Pompe", "Suivez le niveau du réservoir, le débit et le fonctionnement de la pompe avec des alertes configurables."),
    "prod_kit_agri_field_node": _copy(
        "GV Soil — Nó Agrícola Solar", "Solo, temperatura, humidade e chuva num nó de campo; configuração final por local.",
        "GV Soil — Solar Farm Node", "Soil, temperature, humidity and rain in one field node; final configuration is site-specific.",
        "GV Soil — Nodo Agrícola Solar", "Suelo, temperatura, humedad y lluvia en un nodo de campo; configuración final según el sitio.",
        "GV Soil — Nœud Agricole Solaire", "Sol, température, humidité et pluie dans un nœud de terrain ; configuration finale selon le site."),
    "prod_kit_facility_guard": _copy(
        "GV Site — Propriedade e Fugas", "Porta, movimento e deteção de água para pequenas propriedades, com histórico e alertas.",
        "GV Site — Property & Leaks", "Door, motion and water detection for small properties, with history and alerts.",
        "GV Site — Propiedad y Fugas", "Detección de puertas, movimiento y agua para pequeñas propiedades, con historial y alertas.",
        "GV Site — Propriété et Fuites", "Détection de porte, mouvement et eau pour petites propriétés, avec historique et alertes."),
    "prod_kit_environment_air": _copy(
        "GV Air — Ambiente e Conforto", "CO₂, partículas, temperatura, humidade e ruído para espaços interiores ou exteriores.",
        "GV Air — Environment & Comfort", "CO₂, particles, temperature, humidity and noise for indoor or outdoor spaces.",
        "GV Air — Ambiente y Confort", "CO₂, partículas, temperatura, humedad y ruido para espacios interiores o exteriores.",
        "GV Air — Environnement et Confort", "CO₂, particules, température, humidité et bruit pour espaces intérieurs ou extérieurs."),
    "prod_kit_energy_meter_starter": _copy(
        "GV Power — Energia e Consumo", "Tensão, corrente, potência e energia com alertas de carga elevada — para controlar o consumo em casa ou na propriedade.",
        "GV Power — Energy & Consumption", "Voltage, current, power and energy with high-load alerts — to keep household or property consumption under control.",
        "GV Power — Energía y Consumo", "Tensión, corriente, potencia y energía con alertas de carga elevada — para controlar el consumo en casa o en la propiedad.",
        "GV Power — Énergie et Consommation", "Tension, courant, puissance et énergie avec alertes de forte charge — pour maîtriser la consommation du foyer ou de la propriété."),
    "prod_kit_gps_asset_tracker": _copy(
        "GV Track — Ativos Móveis", "Localização, movimento, bateria e sinal para ativos compatíveis.",
        "GV Track — Mobile Assets", "Location, movement, battery and signal for compatible mobile assets.",
        "GV Track — Activos Móviles", "Ubicación, movimiento, batería y señal de activos compatibles.",
        "GV Track — Actifs Mobiles", "Position, mouvement, batterie et signal pour les actifs compatibles."),
    "prod_kit_soil_control": _copy(
        "GV SoilControl — Irrigação Monitorizada", "Solo, nível e caudal com opção de válvula de baixa tensão, sujeito a validação da instalação.",
        "GV SoilControl — Monitored Irrigation", "Soil, level and flow monitoring with an optional low-voltage valve, subject to installation validation.",
        "GV SoilControl — Riego Monitorizado", "Suelo, nivel y caudal con válvula opcional de baja tensión, sujeto a validación de la instalación.",
        "GV SoilControl — Irrigation Surveillée", "Sol, niveau et débit avec vanne basse tension en option, sous réserve de validation de l’installation."),
    "prod_kit_agro_weather": _copy(
        "GV AgroWeather — Estação de Campo", "Temperatura, humidade, pressão, chuva, vento e radiação para apoiar o trabalho agrícola.",
        "GV AgroWeather — Field Station", "Temperature, humidity, pressure, rain, wind and radiation to support farm operations.",
        "GV AgroWeather — Estación de Campo", "Temperatura, humedad, presión, lluvia, viento y radiación para apoyar el trabajo agrícola.",
        "GV AgroWeather — Station de Terrain", "Température, humidité, pression, pluie, vent et rayonnement pour les opérations agricoles."),
    "prod_kit_greenhouse_control": _copy(
        "GV Greenhouse — Clima de Estufa", "Clima, substrato, CO₂ e luz, com controlo opcional de baixa tensão.",
        "GV Greenhouse — Greenhouse Climate", "Climate, substrate, CO₂ and light with optional low-voltage control.",
        "GV Greenhouse — Clima de Invernadero", "Clima, sustrato, CO₂ y luz con control opcional de baja tensión.",
        "GV Greenhouse — Climat de Serre", "Climat, substrat, CO₂ et lumière avec commande basse tension en option."),
    "prod_kit_input_track": _copy(
        "GV InputTrack — Insumos e Ativos", "Localização e nível de stock para apoiar registos de equipamento e reposição.",
        "GV InputTrack — Inputs & Assets", "Location and stock-level tracking to support equipment records and replenishment.",
        "GV InputTrack — Insumos y Activos", "Ubicación y nivel de existencias para apoyar registros de equipos y reposición.",
        "GV InputTrack — Intrants et Actifs", "Localisation et niveau de stock pour faciliter le suivi des équipements et le réapprovisionnement."),
}


_SERVICE_PRODUCT_IDS = {
    "prod_infra_progress", "prod_infra_inspection",
    "prod_aerial_basic_mapping", "prod_agro_visual_inspection",
}

_GENERIC_DELIVERABLES = {
    "service": {
        "en": ["Mapped visual evidence", "Technical summary", "Agreed output files"],
        "es": ["Evidencia visual cartografiada", "Resumen técnico", "Archivos de entrega acordados"],
        "fr": ["Preuves visuelles cartographiées", "Synthèse technique", "Fichiers de livraison convenus"],
    },
    "hardware": {
        "en": ["Selected hardware", "Connection guide", "Compatibility check"],
        "es": ["Hardware seleccionado", "Guía de conexión", "Verificación de compatibilidad"],
        "fr": ["Matériel sélectionné", "Guide de connexion", "Vérification de compatibilité"],
    },
    "kit": {
        "en": ["Configured monitoring kit", "Live dashboard", "Configurable alerts"],
        "es": ["Kit de monitorización configurado", "Panel en directo", "Alertas configurables"],
        "fr": ["Kit de suivi configuré", "Tableau de bord en direct", "Alertes configurables"],
    },
}


def get_product_translations(product_id: str) -> dict[str, dict[str, Any]]:
    source = PUBLIC_PRODUCT_TRANSLATIONS.get(product_id, {})
    if not source:
        return {}
    kind = "service" if product_id in _SERVICE_PRODUCT_IDS else (
        "kit" if product_id.startswith("prod_kit_") else "hardware"
    )
    result: dict[str, dict[str, Any]] = {}
    for language, values in source.items():
        result[language] = dict(values)
        localized_items = _GENERIC_DELIVERABLES[kind].get(language)
        if localized_items:
            result[language]["deliverables"] = list(localized_items)
    return result
