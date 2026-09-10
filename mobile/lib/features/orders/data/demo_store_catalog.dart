import '../domain/product.dart';

/// A small offline catalogue made only from products that are active in the
/// production first-party catalogue. The API remains authoritative outside demo mode.
abstract final class DemoStoreCatalog {
  static const products = <GvProduct>[
    GvProduct(
      id: 'prod_infra_progress_survey',
      name: 'Levantamento de Progresso de Infraestrutura',
      category: 'service',
      priceCents: 66500,
      priceAkzCents: 55000000,
      priceEurCents: 61100,
      currency: 'USD',
      featured: true,
      sectors: ['construction', 'infrastructure'],
      image: 'assets/images/store/construction-progress.jpg',
      description:
          'Levantamento RGB/RTK recorrente para comparar progresso apenas quando existem evidências de levantamento e planeamento válidas.',
      deliverables: [
        'Ortomosaico atual',
        'Comparação com levantamento anterior',
        'Relatório de progresso com evidências'
      ],
      translations: {
        'en': {
          'name': 'Infrastructure Progress Survey',
          'description':
              'Repeat RGB/RTK survey for progress comparison only when valid survey and planning evidence exists.'
        },
        'es': {
          'name': 'Levantamiento de Progreso de Infraestructura',
          'description':
              'Levantamiento RGB/RTK repetido para comparar el progreso solo con datos válidos de levantamiento y planificación.'
        },
        'fr': {
          'name': 'Relevé d’avancement d’infrastructure',
          'description':
              'Relevé RGB/RTK répété pour comparer l’avancement uniquement avec des données de relevé et de planification valides.'
        },
      },
    ),
    GvProduct(
      id: 'prod_infra_technical_inspection',
      name: 'Inspeção Técnica de Infraestrutura',
      category: 'service',
      priceCents: 54500,
      priceAkzCents: 45000000,
      priceEurCents: 50000,
      currency: 'USD',
      sectors: ['construction', 'infrastructure'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Observações visuais georreferenciadas para revisão qualificada; não constitui diagnóstico de engenharia.',
      deliverables: [
        'Fotografias georreferenciadas',
        'Registo de áreas para revisão',
        'Relatório ligado às evidências'
      ],
      translations: {
        'en': {
          'name': 'Infrastructure Technical Inspection',
          'description':
              'Georeferenced visual observations for qualified review; not an engineering diagnosis.'
        },
        'es': {
          'name': 'Inspección Técnica de Infraestructura',
          'description':
              'Observaciones visuales georreferenciadas para revisión cualificada; no constituyen un diagnóstico de ingeniería.'
        },
        'fr': {
          'name': 'Inspection technique d’infrastructure',
          'description':
              'Observations visuelles géoréférencées pour examen qualifié ; elles ne constituent pas un diagnostic d’ingénierie.'
        },
      },
    ),
    GvProduct(
      id: 'prod_infra_thermal_inspection',
      name: 'Inspeção Térmica de Infraestrutura',
      category: 'service',
      priceCents: 57500,
      priceAkzCents: 47500000,
      priceEurCents: 52800,
      currency: 'USD',
      sectors: ['infrastructure'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Regista anomalias de temperatura quando existem dados térmicos calibrados; não classifica anomalias como avarias.',
      deliverables: [
        'Imagens térmicas',
        'Registo de anomalias de temperatura',
        'Relatório ligado às evidências'
      ],
      translations: {
        'en': {
          'name': 'Infrastructure Thermal Inspection',
          'description':
              'Records temperature anomalies from calibrated thermal data without labelling them as faults.'
        },
        'es': {
          'name': 'Inspección Térmica de Infraestructura',
          'description':
              'Registra anomalías de temperatura a partir de datos térmicos calibrados sin clasificarlas como fallos.'
        },
        'fr': {
          'name': 'Inspection thermique d’infrastructure',
          'description':
              'Consigne les anomalies de température issues de données thermiques étalonnées sans les qualifier de défaillances.'
        },
      },
    ),
    GvProduct(
      id: 'prod_infra_3d_mapping',
      name: 'Mapeamento 3D de Infraestrutura',
      category: 'service',
      priceCents: 150500,
      priceAkzCents: 125000000,
      priceEurCents: 138900,
      currency: 'USD',
      sectors: ['infrastructure'],
      image: 'assets/images/store/construction-progress.jpg',
      description:
          'Contexto 3D medido por fotogrametria ou LiDAR, conforme a fonte de aquisição validada.',
      deliverables: [
        'Nuvem de pontos georreferenciada',
        'Malha 3D quando suportada',
        'DSM ou DTM quando suportado'
      ],
      translations: {
        'en': {
          'name': 'Infrastructure 3D Mapping',
          'description':
              'Measured 3D context from photogrammetry or LiDAR, according to the validated acquisition source.'
        },
        'es': {
          'name': 'Cartografía 3D de Infraestructura',
          'description':
              'Contexto 3D medido mediante fotogrametría o LiDAR, según la fuente de adquisición validada.'
        },
        'fr': {
          'name': 'Cartographie 3D d’infrastructure',
          'description':
              'Contexte 3D mesuré par photogrammétrie ou LiDAR, selon la source d’acquisition validée.'
        },
      },
    ),
    GvProduct(
      id: 'prod_infra_specialist_review',
      name: 'Revisão Especializada de Infraestrutura',
      category: 'service',
      priceCents: 24100,
      priceAkzCents: 20000000,
      priceEurCents: 22200,
      currency: 'USD',
      sectors: ['infrastructure'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Revisão qualificada das evidências e áreas sinalizadas, preservando as observações e a proveniência originais.',
      deliverables: [
        'Registo da revisão',
        'Notas do especialista',
        'Decisão de seguimento documentada'
      ],
      translations: {
        'en': {
          'name': 'Infrastructure Specialist Review',
          'description':
              'Qualified review of evidence and flagged areas while preserving original observations and provenance.'
        },
        'es': {
          'name': 'Revisión Especializada de Infraestructura',
          'description':
              'Revisión cualificada de evidencias y áreas señaladas, preservando las observaciones y la procedencia originales.'
        },
        'fr': {
          'name': 'Examen spécialisé d’infrastructure',
          'description':
              'Examen qualifié des preuves et zones signalées, tout en préservant les observations et la provenance d’origine.'
        },
      },
    ),
    GvProduct(
      id: 'prod_infra_monitoring_plan',
      name: 'Plano de Monitorização de Infraestrutura',
      category: 'subscription',
      priceCents: 60300,
      priceAkzCents: 50000000,
      priceEurCents: 55500,
      currency: 'USD',
      featured: true,
      sectors: ['infrastructure'],
      image: 'assets/images/store/construction-progress.jpg',
      description:
          'Levantamentos recorrentes, controlos de qualidade, comparações e relatórios rastreáveis com cadência acordada.',
      deliverables: [
        'Calendário de monitorização',
        'Histórico de comparações',
        'Relatório recorrente com evidências'
      ],
      translations: {
        'en': {
          'name': 'Infrastructure Monitoring Plan',
          'description':
              'Recurring surveys, quality checks, comparisons and traceable reports on an agreed cadence.'
        },
        'es': {
          'name': 'Plan de Monitorización de Infraestructura',
          'description':
              'Levantamientos recurrentes, controles de calidad, comparaciones e informes trazables con una frecuencia acordada.'
        },
        'fr': {
          'name': 'Plan de suivi d’infrastructure',
          'description':
              'Relevés récurrents, contrôles qualité, comparaisons et rapports traçables selon une fréquence convenue.'
        },
      },
    ),
    GvProduct(
      id: 'prod_env_environmental_survey',
      name: 'Levantamento de Evidências Ambientais',
      category: 'service',
      priceCents: 57800,
      priceAkzCents: 48000000,
      priceEurCents: 53300,
      currency: 'USD',
      featured: true,
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Levantamento multifuente de condições observadas e possíveis mudanças, sem atribuir causas ou emitir conclusões regulamentares.',
      deliverables: [
        'Mapa ambiental ligado às fontes',
        'Registo de condições observadas',
        'Relatório ligado às evidências'
      ],
      translations: {
        'en': {
          'name': 'Environmental Evidence Survey',
          'description':
              'Multi-source survey of observed conditions and possible change without assigning causes or making regulatory conclusions.'
        },
        'es': {
          'name': 'Levantamiento de Evidencias Ambientales',
          'description':
              'Levantamiento multifuente de condiciones observadas y posibles cambios, sin atribuir causas ni emitir conclusiones regulatorias.'
        },
        'fr': {
          'name': 'Relevé de preuves environnementales',
          'description':
              'Relevé multisource des conditions observées et des changements possibles, sans attribuer de cause ni tirer de conclusion réglementaire.'
        },
      },
    ),
    GvProduct(
      id: 'prod_env_reforestation_monitoring',
      name: 'Monitorização da Reflorestação',
      category: 'subscription',
      priceCents: 62700,
      priceAkzCents: 52000000,
      priceEurCents: 57800,
      currency: 'USD',
      featured: true,
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Observações repetidas por satélite e drone para tendências de vegetação e restauração sustentadas por fontes, sem diagnóstico automático da causa.',
      deliverables: [
        'Comparação multitemporal da vegetação',
        'Histórico de observações da restauração',
        'Relatório recorrente com evidências'
      ],
      translations: {
        'en': {
          'name': 'Reforestation Monitoring',
          'description':
              'Repeat satellite and drone observations for source-backed vegetation and restoration trends without automatic cause diagnosis.'
        },
        'es': {
          'name': 'Monitorización de la Reforestación',
          'description':
              'Observaciones repetidas por satélite y dron para tendencias de vegetación y restauración respaldadas por fuentes, sin diagnóstico automático de la causa.'
        },
        'fr': {
          'name': 'Suivi du reboisement',
          'description':
              'Observations répétées par satellite et drone des tendances de végétation et de restauration, avec sources et sans diagnostic automatique de la cause.'
        },
      },
    ),
    GvProduct(
      id: 'prod_env_targeted_drone_verification',
      name: 'Verificação Ambiental Direcionada por Drone',
      category: 'service',
      priceCents: 43400,
      priceAkzCents: 36000000,
      priceEurCents: 40000,
      currency: 'USD',
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Evidências aéreas de maior resolução numa área sinalizada por satélite, para revisão especializada e sem confirmação automática da causa.',
      deliverables: [
        'Imagens georreferenciadas direcionadas',
        'Registo da área sinalizada',
        'Pacote de evidências de verificação'
      ],
      translations: {
        'en': {
          'name': 'Targeted Drone Verification',
          'description':
              'Higher-resolution aerial evidence for a satellite-flagged area, for specialist review without automatically confirming a cause.'
        },
        'es': {
          'name': 'Verificación Ambiental Dirigida con Dron',
          'description':
              'Evidencia aérea de mayor resolución para un área señalada por satélite, destinada a revisión especializada sin confirmar automáticamente una causa.'
        },
        'fr': {
          'name': 'Vérification environnementale ciblée par drone',
          'description':
              'Preuves aériennes de meilleure résolution pour une zone signalée par satellite, destinées à un examen spécialisé sans confirmer automatiquement une cause.'
        },
      },
    ),
    GvProduct(
      id: 'prod_env_sensor_installation',
      name: 'Instalação de Sensores Ambientais',
      category: 'service',
      priceCents: 35000,
      priceAkzCents: 29000000,
      priceEurCents: 32200,
      currency: 'USD',
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Instalação e colocação em serviço específicas do local, sujeitas à validação do equipamento, localização, calibração e conectividade.',
      deliverables: [
        'Registo de instalação e localização',
        'Controlos de colocação em serviço',
        'Notas de proveniência e manutenção'
      ],
      translations: {
        'en': {
          'name': 'Environmental Sensor Installation',
          'description':
              'Site-specific installation and commissioning subject to validation of equipment, placement, calibration, and connectivity.'
        },
        'es': {
          'name': 'Instalación de Sensores Ambientales',
          'description':
              'Instalación y puesta en servicio específicas del sitio, sujetas a la validación del equipo, la ubicación, la calibración y la conectividad.'
        },
        'fr': {
          'name': 'Installation de capteurs environnementaux',
          'description':
              'Installation et mise en service propres au site, sous réserve de validation du matériel, du positionnement, de l’étalonnage et de la connectivité.'
        },
      },
    ),
    GvProduct(
      id: 'prod_env_monitoring_plan',
      name: 'Plano de Monitorização Ambiental',
      category: 'subscription',
      priceCents: 54200,
      priceAkzCents: 45000000,
      priceEurCents: 50000,
      currency: 'USD',
      featured: true,
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Plano recorrente de observações por satélite, campo, sensores ou drone, com controlos de qualidade e relatórios rastreáveis.',
      deliverables: [
        'Cadência e plano de fontes',
        'Histórico de observações com qualidade controlada',
        'Relatório recorrente com evidências'
      ],
      translations: {
        'en': {
          'name': 'Environmental Monitoring Plan',
          'description':
              'Recurring satellite, field, sensor, or drone observation plan with quality checks and traceable reports.'
        },
        'es': {
          'name': 'Plan de Monitorización Ambiental',
          'description':
              'Plan recurrente de observaciones por satélite, campo, sensores o dron, con controles de calidad e informes trazables.'
        },
        'fr': {
          'name': 'Plan de suivi environnemental',
          'description':
              'Plan récurrent d’observations par satellite, sur le terrain, par capteurs ou par drone, avec contrôles qualité et rapports traçables.'
        },
      },
    ),
    GvProduct(
      id: 'prod_env_specialist_review',
      name: 'Revisão por Especialista Ambiental',
      category: 'service',
      priceCents: 24100,
      priceAkzCents: 20000000,
      priceEurCents: 22200,
      currency: 'USD',
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Revisão qualificada de evidências e possíveis mudanças, preservando as observações, incertezas, proveniência e limitações originais.',
      deliverables: [
        'Registo da revisão de evidências',
        'Notas de interpretação especializada',
        'Decisão de seguimento documentada'
      ],
      translations: {
        'en': {
          'name': 'Environmental Specialist Review',
          'description':
              'Qualified review of evidence and possible change while preserving original observations, uncertainty, provenance, and limitations.'
        },
        'es': {
          'name': 'Revisión por Especialista Ambiental',
          'description':
              'Revisión cualificada de evidencias y posibles cambios que conserva las observaciones, la incertidumbre, la procedencia y las limitaciones originales.'
        },
        'fr': {
          'name': 'Examen par un spécialiste environnemental',
          'description':
              'Examen qualifié des preuves et changements possibles, préservant les observations, l’incertitude, la provenance et les limites d’origine.'
        },
      },
    ),
    GvProduct(
      id: 'prod_aerial_basic_mapping',
      name: 'Mapeamento Aéreo Essencial',
      category: 'service',
      priceCents: 42500,
      priceAkzCents: 35000000,
      priceEurCents: 38900,
      currency: 'USD',
      featured: true,
      sectors: ['agro', 'environment', 'infrastructure'],
      image: 'assets/images/store/multispectral-drone-service.jpg',
      description:
          'Mapeamento visual de uma exploração, propriedade ou local com ortomosaico e resumo de observações.',
      deliverables: [
        'Ortomosaico visual',
        'Fotografias georreferenciadas',
        'Resumo de observações'
      ],
      translations: {
        'en': {
          'name': 'Essential Aerial Mapping',
          'description':
              'Visual mapping of a farm, property or site with an orthomosaic and observation summary.'
        },
        'es': {
          'name': 'Cartografía Aérea Esencial',
          'description':
              'Cartografía visual de una explotación, propiedad o sitio con ortomosaico y resumen de observaciones.'
        },
        'fr': {
          'name': 'Cartographie aérienne essentielle',
          'description':
              'Cartographie visuelle d’une exploitation, propriété ou site avec orthomosaïque et synthèse.'
        },
      },
    ),
    GvProduct(
      id: 'prod_agro_visual_inspection',
      name: 'Inspeção Visual Agrícola',
      category: 'service',
      priceCents: 30500,
      priceAkzCents: 25000000,
      priceEurCents: 27800,
      currency: 'USD',
      sectors: ['agro'],
      image: 'assets/images/store/multispectral-drone-service.jpg',
      description:
          'Inspeção aérea para documentar culturas, irrigação, acessos e anomalias visíveis.',
      deliverables: [
        'Fotografias aéreas',
        'Mapa de observações',
        'Relatório visual'
      ],
      translations: {
        'en': {
          'name': 'Visual Farm Inspection',
          'description':
              'Aerial inspection documenting crops, irrigation, access and visible anomalies.'
        },
        'es': {
          'name': 'Inspección Visual Agrícola',
          'description':
              'Inspección aérea para documentar cultivos, riego, accesos y anomalías visibles.'
        },
        'fr': {
          'name': 'Inspection visuelle agricole',
          'description':
              'Inspection aérienne des cultures, de l’irrigation, des accès et anomalies visibles.'
        },
      },
    ),
    GvProduct(
      id: 'prod_supply_soil_probe',
      name: 'Kit de Sondas de Solo',
      category: 'hardware',
      priceCents: 3000,
      priceAkzCents: 2550000,
      priceEurCents: 2800,
      currency: 'USD',
      sectors: ['agro'],
      image: 'assets/images/store/soil-iot-kit.jpg',
      description:
          'Sondas de humidade para substituição, expansão ou primeiro protótipo, sujeitas a verificação de compatibilidade.',
      deliverables: [
        'Duas sondas',
        'Guia de ligação',
        'Verificação de compatibilidade'
      ],
      translations: {
        'en': {
          'name': 'Soil Probe Kit',
          'description':
              'Moisture probes for replacement, expansion or a first prototype, subject to compatibility checks.'
        },
        'es': {
          'name': 'Kit de Sondas de Suelo',
          'description':
              'Sondas de humedad para sustitución, ampliación o primer prototipo, sujetas a compatibilidad.'
        },
        'fr': {
          'name': 'Kit de sondes de sol',
          'description':
              'Sondes d’humidité pour remplacement, extension ou premier prototype, sous réserve de compatibilité.'
        },
      },
    ),
    GvProduct(
      id: 'prod_supply_irrigation_parts',
      name: 'Kit de Componentes de Irrigação',
      category: 'hardware',
      priceCents: 5000,
      priceAkzCents: 4250000,
      priceEurCents: 4600,
      currency: 'USD',
      sectors: ['agro'],
      image: 'assets/images/store/soil-iot-kit.jpg',
      description:
          'Válvula de baixa tensão, sensor de caudal e ligações para um protótipo de irrigação monitorizada.',
      deliverables: ['Válvula', 'Sensor de caudal', 'Conectores e guia'],
      translations: {
        'en': {
          'name': 'Irrigation Components Kit',
          'description':
              'Low-voltage valve, flow sensor and fittings for a monitored irrigation prototype.'
        },
        'es': {
          'name': 'Kit de Componentes de Riego',
          'description':
              'Válvula de baja tensión, sensor de caudal y conexiones para un prototipo monitorizado.'
        },
        'fr': {
          'name': 'Kit de composants d’irrigation',
          'description':
              'Vanne basse tension, capteur de débit et raccords pour un prototype d’irrigation surveillée.'
        },
      },
    ),
    GvProduct(
      id: 'prod_kit_water_tank_starter',
      name: 'GV Level — Água e Bomba',
      category: 'hardware',
      priceCents: 13000,
      priceAkzCents: 11050000,
      priceEurCents: 12000,
      currency: 'USD',
      featured: true,
      sectors: ['infrastructure'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'Acompanhe nível do depósito, caudal e funcionamento da bomba com alertas configuráveis.',
      deliverables: [
        'Kit de sensores',
        'Painel em direto',
        'Alertas configuráveis'
      ],
      translations: {
        'en': {
          'name': 'GV Level — Water & Pump',
          'description':
              'Track tank level, flow and pump operation with configurable alerts.'
        },
        'es': {
          'name': 'GV Level — Agua y Bomba',
          'description':
              'Supervisa el nivel, el caudal y la bomba con alertas configurables.'
        },
        'fr': {
          'name': 'GV Level — Eau et pompe',
          'description':
              'Suivez le niveau, le débit et la pompe avec des alertes configurables.'
        },
      },
    ),
    GvProduct(
      id: 'prod_kit_environment_air',
      name: 'GV Air — Ambiente e Conforto',
      category: 'hardware',
      priceCents: 14000,
      priceAkzCents: 11900000,
      priceEurCents: 12900,
      currency: 'USD',
      sectors: ['environment'],
      image: 'assets/images/store/environmental-monitoring.jpg',
      description:
          'CO₂, partículas, temperatura, humidade e ruído para espaços interiores ou exteriores.',
      deliverables: ['Kit de sensores', 'Histórico', 'Alertas configuráveis'],
      translations: {
        'en': {
          'name': 'GV Air — Environment & Comfort',
          'description':
              'CO₂, particles, temperature, humidity and noise for indoor or outdoor spaces.'
        },
        'es': {
          'name': 'GV Air — Ambiente y Confort',
          'description':
              'CO₂, partículas, temperatura, humedad y ruido para espacios interiores o exteriores.'
        },
        'fr': {
          'name': 'GV Air — Environnement et confort',
          'description':
              'CO₂, particules, température, humidité et bruit pour espaces intérieurs ou extérieurs.'
        },
      },
    ),
  ];
}
