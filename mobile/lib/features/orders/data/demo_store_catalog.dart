import '../domain/product.dart';

/// A small offline catalogue made only from products that are active in the
/// production marketplace. The API remains authoritative outside demo mode.
abstract final class DemoStoreCatalog {
  static const products = <GvProduct>[
    GvProduct(
      id: 'prod_infra_progress',
      name: 'Monitorização de Progresso de Obra',
      category: 'service',
      priceCents: 66500,
      priceAkzCents: 55000000,
      priceEurCents: 61100,
      currency: 'USD',
      featured: true,
      sectors: ['construction', 'infrastructure'],
      image: 'assets/images/store/construction-progress.jpg',
      description:
          'Acompanhamento visual e volumétrico do progresso da construção, com evidências periódicas.',
      deliverables: ['Ortomosaico', 'Modelo 3D', 'Relatório de progresso'],
      translations: {
        'en': {
          'name': 'Construction Progress Monitoring',
          'description':
              'Visual and volumetric construction progress tracking with periodic evidence.'
        },
        'es': {
          'name': 'Seguimiento del Progreso de Obra',
          'description':
              'Seguimiento visual y volumétrico del progreso de la obra con evidencias periódicas.'
        },
        'fr': {
          'name': 'Suivi de l’avancement des travaux',
          'description':
              'Suivi visuel et volumétrique du chantier avec des preuves périodiques.'
        },
      },
    ),
    GvProduct(
      id: 'prod_infra_inspection',
      name: 'Inspeção Visual de Estruturas',
      category: 'service',
      priceCents: 54500,
      priceAkzCents: 45000000,
      priceEurCents: 50000,
      currency: 'USD',
      sectors: ['construction', 'infrastructure'],
      image: 'assets/images/store/infrastructure-inspection.jpg',
      description:
          'Inspeção visual de pontes, torres e edifícios, com evidências anotadas para revisão técnica.',
      deliverables: ['Relatório de inspeção', 'Fotografias anotadas', 'Vídeo'],
      translations: {
        'en': {
          'name': 'Visual Structure Inspection',
          'description':
              'Visual inspection of bridges, towers and buildings with annotated evidence for technical review.'
        },
        'es': {
          'name': 'Inspección Visual de Estructuras',
          'description':
              'Inspección visual de puentes, torres y edificios con evidencias anotadas para revisión técnica.'
        },
        'fr': {
          'name': 'Inspection visuelle des structures',
          'description':
              'Inspection visuelle de ponts, tours et bâtiments avec preuves annotées pour examen technique.'
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
