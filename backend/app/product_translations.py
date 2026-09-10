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
    "prod_infra_progress_survey": _copy(
        "Levantamento de Progresso de Infraestrutura",
        "Levantamento RGB/RTK recorrente para comparar progresso apenas quando existem evidências de levantamento e planeamento válidas.",
        "Infrastructure Progress Survey",
        "Repeat RGB/RTK survey for progress comparison only when valid survey and planning evidence exists.",
        "Levantamiento de Progreso de Infraestructura",
        "Levantamiento RGB/RTK repetido para comparar el progreso solo cuando existen datos válidos de levantamiento y planificación.",
        "Relevé d’Avancement d’Infrastructure",
        "Relevé RGB/RTK répété pour comparer l’avancement uniquement avec des données de relevé et de planification valides.",
    ),
    "prod_infra_technical_inspection": _copy(
        "Inspeção Técnica de Infraestrutura",
        "Observações visuais georreferenciadas para revisão qualificada; não constitui diagnóstico de engenharia.",
        "Infrastructure Technical Inspection",
        "Georeferenced visual observations for qualified review; not an engineering diagnosis.",
        "Inspección Técnica de Infraestructura",
        "Observaciones visuales georreferenciadas para revisión cualificada; no constituyen un diagnóstico de ingeniería.",
        "Inspection Technique d’Infrastructure",
        "Observations visuelles géoréférencées pour examen qualifié ; elles ne constituent pas un diagnostic d’ingénierie.",
    ),
    "prod_infra_thermal_inspection": _copy(
        "Inspeção Térmica de Infraestrutura",
        "Regista anomalias de temperatura quando existem dados térmicos calibrados; não classifica anomalias como avarias.",
        "Infrastructure Thermal Inspection",
        "Records temperature anomalies from calibrated thermal data without labelling them as faults.",
        "Inspección Térmica de Infraestructura",
        "Registra anomalías de temperatura a partir de datos térmicos calibrados sin clasificarlas como fallos.",
        "Inspection Thermique d’Infrastructure",
        "Consigne les anomalies de température issues de données thermiques étalonnées sans les qualifier de défaillances.",
    ),
    "prod_infra_3d_mapping": _copy(
        "Mapeamento 3D de Infraestrutura",
        "Contexto 3D medido por fotogrametria ou LiDAR, conforme a fonte de aquisição validada.",
        "Infrastructure 3D Mapping",
        "Measured 3D context from photogrammetry or LiDAR, according to the validated acquisition source.",
        "Cartografía 3D de Infraestructura",
        "Contexto 3D medido mediante fotogrametría o LiDAR, según la fuente de adquisición validada.",
        "Cartographie 3D d’Infrastructure",
        "Contexte 3D mesuré par photogrammétrie ou LiDAR, selon la source d’acquisition validée.",
    ),
    "prod_infra_specialist_review": _copy(
        "Revisão Especializada de Infraestrutura",
        "Revisão qualificada das evidências e áreas sinalizadas, preservando as observações e a proveniência originais.",
        "Infrastructure Specialist Review",
        "Qualified review of evidence and flagged areas while preserving original observations and provenance.",
        "Revisión Especializada de Infraestructura",
        "Revisión cualificada de evidencias y áreas señaladas, preservando las observaciones y la procedencia originales.",
        "Examen Spécialisé d’Infrastructure",
        "Examen qualifié des preuves et zones signalées, tout en préservant les observations et la provenance d’origine.",
    ),
    "prod_infra_monitoring_plan": _copy(
        "Plano de Monitorização de Infraestrutura",
        "Levantamentos recorrentes, controlos de qualidade, comparações e relatórios rastreáveis com cadência acordada.",
        "Infrastructure Monitoring Plan",
        "Recurring surveys, quality checks, comparisons and traceable reports on an agreed cadence.",
        "Plan de Monitorización de Infraestructura",
        "Levantamientos recurrentes, controles de calidad, comparaciones e informes trazables con una frecuencia acordada.",
        "Plan de Suivi d’Infrastructure",
        "Relevés récurrents, contrôles qualité, comparaisons et rapports traçables selon une fréquence convenue.",
    ),
    "prod_env_environmental_survey": _copy(
        "Levantamento de Evidências Ambientais",
        "Levantamento multifuente de condições observadas e possíveis mudanças, sem atribuir causas ou emitir conclusões regulamentares.",
        "Environmental Evidence Survey",
        "Multi-source survey of observed conditions and possible change without assigning causes or making regulatory conclusions.",
        "Levantamiento de Evidencias Ambientales",
        "Levantamiento multifuente de condiciones observadas y posibles cambios, sin atribuir causas ni emitir conclusiones regulatorias.",
        "Relevé de Preuves Environnementales",
        "Relevé multisource des conditions observées et des changements possibles, sans attribuer de cause ni tirer de conclusion réglementaire.",
    ),
    "prod_env_reforestation_monitoring": _copy(
        "Monitorização da Reflorestação",
        "Observações repetidas por satélite e drone para tendências de vegetação e restauração sustentadas por fontes, sem diagnóstico automático da causa.",
        "Reforestation Monitoring",
        "Repeat satellite and drone observations for source-backed vegetation and restoration trends without automatic cause diagnosis.",
        "Monitorización de la Reforestación",
        "Observaciones repetidas por satélite y dron para tendencias de vegetación y restauración respaldadas por fuentes, sin diagnóstico automático de la causa.",
        "Suivi du Reboisement",
        "Observations répétées par satellite et drone des tendances de végétation et de restauration, avec sources et sans diagnostic automatique de la cause.",
    ),
    "prod_env_targeted_drone_verification": _copy(
        "Verificação Ambiental Direcionada por Drone",
        "Recolha de evidências aéreas de maior resolução numa área sinalizada por satélite, para revisão especializada e sem confirmação automática da causa.",
        "Targeted Drone Verification",
        "Higher-resolution aerial evidence for a satellite-flagged area, for specialist review without automatically confirming a cause.",
        "Verificación Ambiental Dirigida con Dron",
        "Evidencia aérea de mayor resolución para un área señalada por satélite, destinada a revisión especializada sin confirmar automáticamente una causa.",
        "Vérification Environnementale Ciblée par Drone",
        "Preuves aériennes de meilleure résolution pour une zone signalée par satellite, destinées à un examen spécialisé sans confirmer automatiquement une cause.",
    ),
    "prod_env_sensor_installation": _copy(
        "Instalação de Sensores Ambientais",
        "Instalação e colocação em serviço específicas do local, sujeitas à validação do equipamento, localização, calibração e conectividade.",
        "Environmental Sensor Installation",
        "Site-specific installation and commissioning subject to validation of equipment, placement, calibration, and connectivity.",
        "Instalación de Sensores Ambientales",
        "Instalación y puesta en servicio específicas del sitio, sujetas a la validación del equipo, la ubicación, la calibración y la conectividad.",
        "Installation de Capteurs Environnementaux",
        "Installation et mise en service propres au site, sous réserve de validation du matériel, du positionnement, de l’étalonnage et de la connectivité.",
    ),
    "prod_env_monitoring_plan": _copy(
        "Plano de Monitorização Ambiental",
        "Plano recorrente de observações por satélite, campo, sensores ou drone, com controlos de qualidade e relatórios rastreáveis.",
        "Environmental Monitoring Plan",
        "Recurring satellite, field, sensor, or drone observation plan with quality checks and traceable reports.",
        "Plan de Monitorización Ambiental",
        "Plan recurrente de observaciones por satélite, campo, sensores o dron, con controles de calidad e informes trazables.",
        "Plan de Suivi Environnemental",
        "Plan récurrent d’observations par satellite, sur le terrain, par capteurs ou par drone, avec contrôles qualité et rapports traçables.",
    ),
    "prod_env_specialist_review": _copy(
        "Revisão por Especialista Ambiental",
        "Revisão qualificada de evidências e possíveis mudanças, preservando as observações, incertezas, proveniência e limitações originais.",
        "Environmental Specialist Review",
        "Qualified review of evidence and possible change while preserving original observations, uncertainty, provenance, and limitations.",
        "Revisión por Especialista Ambiental",
        "Revisión cualificada de evidencias y posibles cambios que conserva las observaciones, la incertidumbre, la procedencia y las limitaciones originales.",
        "Examen par un Spécialiste Environnemental",
        "Examen qualifié des preuves et changements possibles, préservant les observations, l’incertitude, la provenance et les limites d’origine.",
    ),
    "prod_mining_volumetry_survey": _copy(
        "Levantamento Volumétrico Mineiro",
        "Levantamento fotogramétrico RTK/PPK para volumes, publicados apenas quando a precisão documentada cumpre as tolerâncias do projeto; não exige LiDAR.",
        "Mining Volumetry Survey",
        "RTK/PPK photogrammetric volume survey, published only when documented accuracy meets project tolerances; LiDAR is not required.",
        "Levantamiento Volumétrico Minero",
        "Levantamiento fotogramétrico RTK/PPK para volúmenes, publicado solo cuando la precisión documentada cumple las tolerancias del proyecto; no requiere LiDAR.",
        "Relevé Volumétrique Minier",
        "Relevé photogrammétrique RTK/PPK des volumes, publié uniquement si la précision documentée respecte les tolérances du projet ; le LiDAR n’est pas requis.",
    ),
    "prod_mining_site_progress_survey": _copy(
        "Levantamento de Progresso Mineiro",
        "Levantamentos repetíveis para mudança medida do terreno, apenas entre fontes compatíveis e sem conclusões sobre minério, reservas ou geotecnia.",
        "Mining Site Progress Survey",
        "Repeatable surveys for measured terrain change between compatible sources, without ore, reserve, or geotechnical conclusions.",
        "Levantamiento de Progreso Minero",
        "Levantamientos repetibles para cambios medidos del terreno entre fuentes compatibles, sin conclusiones sobre mineral, reservas o geotecnia.",
        "Relevé d’Avancement Minier",
        "Relevés répétables des changements mesurés du terrain entre sources compatibles, sans conclusion sur le minerai, les réserves ou la géotechnique.",
    ),
    "prod_mining_lidar_specialist_survey": _copy(
        "Levantamento Especializado LiDAR",
        "Aquisição LiDAR opcional quando os requisitos de acesso, vegetação, geometria ou precisão do projeto a justificam após revisão técnica.",
        "LiDAR Specialist Survey",
        "Optional LiDAR acquisition when project access, vegetation, geometry, or accuracy requirements justify it after technical review.",
        "Levantamiento Especializado LiDAR",
        "Adquisición LiDAR opcional cuando los requisitos de acceso, vegetación, geometría o precisión del proyecto la justifican tras revisión técnica.",
        "Relevé Spécialisé LiDAR",
        "Acquisition LiDAR facultative lorsque les exigences d’accès, de végétation, de géométrie ou de précision du projet la justifient après examen technique.",
    ),
    "prod_mining_environmental_monitoring": _copy(
        "Monitorização Ambiental Mineira",
        "Observações rastreáveis de zonas acordadas, sem determinar automaticamente impacto, conformidade ou causa.",
        "Mining Environmental Monitoring",
        "Traceable observations of agreed monitoring zones without automatically determining impact, compliance, or causation.",
        "Monitorización Ambiental Minera",
        "Observaciones trazables de zonas acordadas sin determinar automáticamente el impacto, el cumplimiento o la causa.",
        "Suivi Environnemental Minier",
        "Observations traçables des zones convenues sans déterminer automatiquement l’impact, la conformité ou la cause.",
    ),
    "prod_mining_repeat_monitoring_plan": _copy(
        "Plano de Monitorização Mineira Recorrente",
        "Plano recorrente centrado no ativo, com tolerâncias acordadas, controlos de qualidade, comparações históricas e relatórios rastreáveis.",
        "Mining Repeat Monitoring Plan",
        "Recurring asset-centric plan with agreed tolerances, quality controls, historical comparisons, and traceable reports.",
        "Plan de Monitorización Minera Recurrente",
        "Plan recurrente centrado en el activo con tolerancias acordadas, controles de calidad, comparaciones históricas e informes trazables.",
        "Plan de Suivi Minier Récurrent",
        "Plan récurrent centré sur l’actif, avec tolérances convenues, contrôles qualité, comparaisons historiques et rapports traçables.",
    ),
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
    "prod_infra_progress_survey", "prod_infra_technical_inspection",
    "prod_infra_thermal_inspection", "prod_infra_3d_mapping",
    "prod_infra_specialist_review", "prod_infra_monitoring_plan",
    "prod_env_environmental_survey", "prod_env_reforestation_monitoring",
    "prod_env_targeted_drone_verification", "prod_env_sensor_installation",
    "prod_env_monitoring_plan", "prod_env_specialist_review",
    "prod_mining_volumetry_survey", "prod_mining_site_progress_survey",
    "prod_mining_lidar_specialist_survey", "prod_mining_environmental_monitoring",
    "prod_mining_repeat_monitoring_plan",
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
