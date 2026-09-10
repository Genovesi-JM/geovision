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
      id: 'prod_mining_volumetry_survey',
      name: 'Levantamento Volumétrico Mineiro',
      category: 'service',
      priceCents: 114500,
      priceAkzCents: 95000000,
      priceEurCents: 105500,
      currency: 'USD',
      featured: true,
      sectors: ['mining'],
      image: 'assets/images/store/mining-drone-survey.jpg',
      description:
          'Levantamento fotogramétrico RTK/PPK para volumes, publicados apenas quando a precisão documentada cumpre as tolerâncias do projeto; não exige LiDAR.',
      deliverables: [
        'Registo de qualidade e pontos de controlo',
        'Resultado volumétrico quando dentro da tolerância',
        'Ortomosaico e modelo de superfície suportado'
      ],
      translations: {
        'en': {
          'name': 'Mining Volumetry Survey',
          'description':
              'RTK/PPK photogrammetric volume survey, published only when documented accuracy meets project tolerances; LiDAR is not required.'
        },
        'es': {
          'name': 'Levantamiento Volumétrico Minero',
          'description':
              'Levantamiento fotogramétrico RTK/PPK para volúmenes, publicado solo cuando la precisión documentada cumple las tolerancias del proyecto; no requiere LiDAR.'
        },
        'fr': {
          'name': 'Relevé volumétrique minier',
          'description':
              'Relevé photogrammétrique RTK/PPK des volumes, publié uniquement si la précision documentée respecte les tolérances du projet ; le LiDAR n’est pas requis.'
        },
      },
    ),
    GvProduct(
      id: 'prod_mining_site_progress_survey',
      name: 'Levantamento de Progresso Mineiro',
      category: 'service',
      priceCents: 84400,
      priceAkzCents: 70000000,
      priceEurCents: 77800,
      currency: 'USD',
      featured: true,
      sectors: ['mining'],
      image: 'assets/images/store/mining-drone-survey.jpg',
      description:
          'Levantamentos repetíveis para mudança medida do terreno, apenas entre fontes compatíveis e sem conclusões sobre minério, reservas ou geotecnia.',
      deliverables: [
        'Levantamento georreferenciado atual',
        'Comparação com levantamento anterior compatível',
        'Relatório de progresso ligado às evidências'
      ],
      translations: {
        'en': {
          'name': 'Mining Site Progress Survey',
          'description':
              'Repeatable surveys for measured terrain change between compatible sources, without ore, reserve, or geotechnical conclusions.'
        },
        'es': {
          'name': 'Levantamiento de Progreso Minero',
          'description':
              'Levantamientos repetibles para cambios medidos del terreno entre fuentes compatibles, sin conclusiones sobre mineral, reservas o geotecnia.'
        },
        'fr': {
          'name': 'Relevé d’avancement minier',
          'description':
              'Relevés répétables des changements mesurés du terrain entre sources compatibles, sans conclusion sur le minerai, les réserves ou la géotechnique.'
        },
      },
    ),
    GvProduct(
      id: 'prod_mining_lidar_specialist_survey',
      name: 'Levantamento Especializado LiDAR',
      category: 'service',
      priceCents: 150500,
      priceAkzCents: 125000000,
      priceEurCents: 138900,
      currency: 'USD',
      sectors: ['mining'],
      image: 'assets/images/store/mining-drone-survey.jpg',
      description:
          'Aquisição LiDAR opcional quando os requisitos de acesso, vegetação, geometria ou precisão do projeto a justificam após revisão técnica.',
      deliverables: [
        'Registo de aquisição e precisão',
        'Nuvem de pontos georreferenciada',
        'Produtos de terreno ou superfície suportados'
      ],
      translations: {
        'en': {
          'name': 'LiDAR Specialist Survey',
          'description':
              'Optional LiDAR acquisition when project access, vegetation, geometry, or accuracy requirements justify it after technical review.'
        },
        'es': {
          'name': 'Levantamiento Especializado LiDAR',
          'description':
              'Adquisición LiDAR opcional cuando los requisitos de acceso, vegetación, geometría o precisión del proyecto la justifican tras revisión técnica.'
        },
        'fr': {
          'name': 'Relevé spécialisé LiDAR',
          'description':
              'Acquisition LiDAR facultative lorsque les exigences d’accès, de végétation, de géométrie ou de précision du projet la justifient après examen technique.'
        },
      },
    ),
    GvProduct(
      id: 'prod_mining_environmental_monitoring',
      name: 'Monitorização Ambiental Mineira',
      category: 'subscription',
      priceCents: 78500,
      priceAkzCents: 65000000,
      priceEurCents: 72200,
      currency: 'USD',
      sectors: ['mining'],
      image: 'assets/images/store/mining-drone-survey.jpg',
      description:
          'Observações rastreáveis de zonas acordadas, sem determinar automaticamente impacto, conformidade ou causa.',
      deliverables: [
        'Mapa de monitorização ligado às fontes',
        'Registo de condições observadas',
        'Resumo de evidências e limitações'
      ],
      translations: {
        'en': {
          'name': 'Mining Environmental Monitoring',
          'description':
              'Traceable observations of agreed monitoring zones without automatically determining impact, compliance, or causation.'
        },
        'es': {
          'name': 'Monitorización Ambiental Minera',
          'description':
              'Observaciones trazables de zonas acordadas sin determinar automáticamente el impacto, el cumplimiento o la causa.'
        },
        'fr': {
          'name': 'Suivi environnemental minier',
          'description':
              'Observations traçables des zones convenues sans déterminer automatiquement l’impact, la conformité ou la cause.'
        },
      },
    ),
    GvProduct(
      id: 'prod_mining_repeat_monitoring_plan',
      name: 'Plano de Monitorização Mineira Recorrente',
      category: 'subscription',
      priceCents: 72300,
      priceAkzCents: 60000000,
      priceEurCents: 66700,
      currency: 'USD',
      featured: true,
      sectors: ['mining'],
      image: 'assets/images/store/mining-drone-survey.jpg',
      description:
          'Plano recorrente centrado no ativo, com tolerâncias acordadas, controlos de qualidade, comparações históricas e relatórios rastreáveis.',
      deliverables: [
        'Cadência e plano de tolerâncias',
        'Histórico de levantamentos e comparações',
        'Relatório recorrente ligado às evidências'
      ],
      translations: {
        'en': {
          'name': 'Mining Repeat Monitoring Plan',
          'description':
              'Recurring asset-centric plan with agreed tolerances, quality controls, historical comparisons, and traceable reports.'
        },
        'es': {
          'name': 'Plan de Monitorización Minera Recurrente',
          'description':
              'Plan recurrente centrado en el activo con tolerancias acordadas, controles de calidad, comparaciones históricas e informes trazables.'
        },
        'fr': {
          'name': 'Plan de suivi minier récurrent',
          'description':
              'Plan récurrent centré sur l’actif, avec tolérances convenues, contrôles qualité, comparaisons historiques et rapports traçables.'
        },
      },
    ),
    GvProduct(
      id: 'prod_ports_visual_inspection',
      name: 'Inspeção Visual Portuária e Industrial',
      category: 'service',
      priceCents: 66500,
      priceAkzCents: 55000000,
      priceEurCents: 61100,
      currency: 'USD',
      featured: true,
      sectors: ['ports'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Evidências RGB georreferenciadas de um ativo e zona exatos; mudanças mapeadas permanecem candidatas para revisão, sem conclusão automática de defeito, segurança ou conformidade.',
      deliverables: [
        'Evidências visuais georreferenciadas',
        'Registo do ativo e zona de inspeção',
        'Relatório de candidatos ligado às evidências'
      ],
      translations: {
        'en': {
          'name': 'Ports & Industrial Visual Inspection',
          'description':
              'Georeferenced RGB evidence for an exact asset and zone; mapped changes remain review candidates without automatic defect, safety, or compliance conclusions.'
        },
        'es': {
          'name': 'Inspección Visual Portuaria e Industrial',
          'description':
              'Evidencia RGB georreferenciada de un activo y zona exactos; los cambios siguen siendo candidatos a revisión, sin conclusiones automáticas de defecto, seguridad o cumplimiento.'
        },
        'fr': {
          'name': 'Inspection visuelle portuaire et industrielle',
          'description':
              'Preuves RGB géoréférencées d’un actif et d’une zone précis ; les changements restent à examiner, sans conclusion automatique de défaut, de sécurité ou de conformité.'
        },
      },
    ),
    GvProduct(
      id: 'prod_ports_thermal_inspection',
      name: 'Inspeção Térmica Portuária e Industrial',
      category: 'service',
      priceCents: 72300,
      priceAkzCents: 60000000,
      priceEurCents: 66700,
      currency: 'USD',
      sectors: ['ports'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Captura térmica calibrada em condições acordadas; diferenças de temperatura permanecem candidatas para revisão e não são classificadas automaticamente como avarias.',
      deliverables: [
        'Imagens térmicas calibradas',
        'Registo de diferenças de temperatura',
        'Condições de aquisição e limitações'
      ],
      translations: {
        'en': {
          'name': 'Ports & Industrial Thermal Inspection',
          'description':
              'Calibrated thermal capture under agreed conditions; temperature differences remain review candidates and are not automatically classified as faults.'
        },
        'es': {
          'name': 'Inspección Térmica Portuaria e Industrial',
          'description':
              'Captura térmica calibrada en condiciones acordadas; las diferencias de temperatura siguen siendo candidatas a revisión y no se clasifican automáticamente como fallos.'
        },
        'fr': {
          'name': 'Inspection thermique portuaire et industrielle',
          'description':
              'Capture thermique étalonnée dans des conditions convenues ; les écarts de température restent à examiner et ne sont pas automatiquement qualifiés de défaillances.'
        },
      },
    ),
    GvProduct(
      id: 'prod_ports_3d_mapping',
      name: 'Captura de Realidade 3D Portuária e Industrial',
      category: 'service',
      priceCents: 144600,
      priceAkzCents: 120000000,
      priceEurCents: 133300,
      currency: 'USD',
      featured: true,
      sectors: ['ports'],
      image: 'assets/images/store/construction-progress.jpg',
      description:
          'Contexto 3D por fotogrametria ou LiDAR tecnicamente justificado, sujeito a registo e qualidade documentados e sem avaliação automática da condição.',
      deliverables: [
        'Nuvem de pontos ou malha quando suportada',
        'Registo e controlo de qualidade',
        'Comparação histórica compatível quando disponível'
      ],
      translations: {
        'en': {
          'name': 'Ports & Industrial 3D Reality Capture',
          'description':
              '3D context from photogrammetry or technically justified LiDAR, subject to documented registration and quality and without automatic condition assessment.'
        },
        'es': {
          'name': 'Captura de Realidad 3D Portuaria e Industrial',
          'description':
              'Contexto 3D mediante fotogrametría o LiDAR técnicamente justificado, sujeto a registro y calidad documentados y sin evaluación automática del estado.'
        },
        'fr': {
          'name': 'Capture de réalité 3D portuaire et industrielle',
          'description':
              'Contexte 3D par photogrammétrie ou LiDAR techniquement justifié, sous réserve d’un recalage et d’une qualité documentés, sans évaluation automatique de l’état.'
        },
      },
    ),
    GvProduct(
      id: 'prod_ports_sensor_installation',
      name: 'Instalação de Sensores Portuários e Industriais',
      category: 'service',
      priceCents: 42200,
      priceAkzCents: 35000000,
      priceEurCents: 38900,
      currency: 'USD',
      sectors: ['ports'],
      image: 'assets/images/store/connected-weather-station.jpg',
      description:
          'Instalação e atribuição auditável de sensores a um ativo GeoVision, sujeitas à validação de localização, calibração, energia, conectividade e comissionamento.',
      deliverables: [
        'Registo de instalação validado',
        'Atribuição auditável ao ativo',
        'Resultado de comissionamento e conectividade'
      ],
      translations: {
        'en': {
          'name': 'Ports & Industrial Sensor Installation',
          'description':
              'Auditable sensor installation and assignment to a GeoVision asset, subject to placement, calibration, power, connectivity, and commissioning validation.'
        },
        'es': {
          'name': 'Instalación de Sensores Portuarios e Industriales',
          'description':
              'Instalación y asignación auditable de sensores a un activo GeoVision, sujetas a validar ubicación, calibración, energía, conectividad y puesta en servicio.'
        },
        'fr': {
          'name': 'Installation de capteurs portuaires et industriels',
          'description':
              'Installation et affectation auditable de capteurs à un actif GeoVision, sous réserve de validation du positionnement, de l’étalonnage, de l’alimentation, de la connectivité et de la mise en service.'
        },
      },
    ),
    GvProduct(
      id: 'prod_ports_monitoring_plan',
      name: 'Plano de Monitorização Portuária e Industrial',
      category: 'subscription',
      priceCents: 90400,
      priceAkzCents: 75000000,
      priceEurCents: 83300,
      currency: 'USD',
      featured: true,
      sectors: ['ports'],
      image: 'assets/images/store/construction-progress.jpg',
      description:
          'Inspeções recorrentes centradas no ativo, contexto de sensores suportados, controlos de qualidade, comparações históricas e relatórios rastreáveis; evidências ausentes permanecem desconhecidas.',
      deliverables: [
        'Cadência de inspeção acordada',
        'Histórico de inspeções e alertas do ativo',
        'Relatórios recorrentes ligados às evidências'
      ],
      translations: {
        'en': {
          'name': 'Ports & Industrial Monitoring Plan',
          'description':
              'Recurring asset-centric inspections, supported sensor context, quality controls, historical comparisons, and traceable reports; missing evidence remains unknown.'
        },
        'es': {
          'name': 'Plan de Monitorización Portuaria e Industrial',
          'description':
              'Inspecciones recurrentes centradas en el activo, contexto de sensores compatibles, controles de calidad, comparaciones históricas e informes trazables; la evidencia ausente permanece desconocida.'
        },
        'fr': {
          'name': 'Plan de suivi portuaire et industriel',
          'description':
              'Inspections récurrentes centrées sur l’actif, contexte de capteurs pris en charge, contrôles qualité, comparaisons historiques et rapports traçables ; les preuves absentes restent inconnues.'
        },
      },
    ),
    GvProduct(
      id: 'prod_ports_specialist_review',
      name: 'Revisão Especializada Portuária e Industrial',
      category: 'service',
      priceCents: 30100,
      priceAkzCents: 25000000,
      priceEurCents: 27800,
      currency: 'USD',
      sectors: ['ports'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Revisão qualificada de evidências e candidatos, preservando observações, incerteza, proveniência e responsabilidade do revisor, sem certificação automática.',
      deliverables: [
        'Registo da revisão das evidências',
        'Autoria e notas de interpretação',
        'Decisão de seguimento documentada'
      ],
      translations: {
        'en': {
          'name': 'Ports & Industrial Specialist Review',
          'description':
              'Qualified review of evidence and candidates while preserving observations, uncertainty, provenance, and reviewer responsibility, without automatic certification.'
        },
        'es': {
          'name': 'Revisión Especializada Portuaria e Industrial',
          'description':
              'Revisión cualificada de evidencias y candidatos que preserva observaciones, incertidumbre, procedencia y responsabilidad del revisor, sin certificación automática.'
        },
        'fr': {
          'name': 'Examen spécialisé portuaire et industriel',
          'description':
              'Examen qualifié des preuves et éléments candidats, préservant observations, incertitude, provenance et responsabilité de l’examinateur, sans certification automatique.'
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
