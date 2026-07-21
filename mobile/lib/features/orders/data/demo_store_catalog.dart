import '../domain/product.dart';

/// Credential-free catalogue aligned with GeoVision's published Supply Hub and
/// sector capabilities. Prices are indicative multi-currency price-list values
/// for UX testing; the production API remains authoritative.
abstract final class DemoStoreCatalog {
  static const products = <GvProduct>[
    GvProduct(
        id: 'agro-ndvi',
        name: 'Análise NDVI/NDRE de culturas',
        category: 'service',
        priceCents: 54500,
        priceAkzCents: 45000000,
        priceEurCents: 50000,
        currency: 'USD',
        unit: 'operação',
        featured: true,
        sectors: ['agro'],
        description:
            'Levantamento com sensor multiespectral para avaliar vigor, stress hídrico, falhas de plantio e variabilidade por parcela. Requer seleção do local e validação da área antes da proposta final.',
        deliverables: [
          'Mapa NDVI e NDRE',
          'Zonas de gestão',
          'Relatório de saúde da cultura'
        ]),
    GvProduct(
        id: 'agro-prescription',
        name: 'Mapa de prescrição agrícola',
        category: 'service',
        priceCents: 36500,
        priceAkzCents: 30000000,
        priceEurCents: 33500,
        currency: 'USD',
        unit: 'projeto',
        sectors: ['agro'],
        description:
            'Transforma dados de campo e imagens multiespectrais em zonas operacionais para aplicação diferenciada. As dosagens finais permanecem sob responsabilidade do cliente ou engenheiro agrónomo.',
        deliverables: [
          'Mapa zonado',
          'Cálculos por hectare',
          'Ficheiro GIS compatível'
        ]),
    GvProduct(
        id: 'agro-spraying',
        name: 'Pulverização de precisão com Agras T40',
        category: 'service',
        priceCents: 42500,
        priceAkzCents: 35000000,
        priceEurCents: 38900,
        currency: 'USD',
        unit: 'operação',
        featured: true,
        sectors: ['agro', 'environment'],
        description:
            'Execução aérea seletiva baseada em mapa de prescrição, com registo da cobertura e consumo. Produto aplicado, dose, condições meteorológicas e autorizações são confirmados antes do agendamento.',
        deliverables: [
          'Plano de operação',
          'Mapa de cobertura',
          'Relatório de aplicação'
        ]),
    GvProduct(
        id: 'agro-irrigation',
        name: 'Diagnóstico de irrigação e stress hídrico',
        category: 'service',
        priceCents: 66500,
        priceAkzCents: 55000000,
        priceEurCents: 61100,
        currency: 'USD',
        unit: 'projeto',
        sectors: ['agro'],
        description:
            'Análise térmica e multiespectral para localizar variações de humidade, possíveis falhas e zonas que requerem inspeção no terreno.',
        deliverables: [
          'Mapa térmico',
          'Mapa de stress hídrico',
          'Lista de zonas prioritárias'
        ]),
    GvProduct(
        id: 'livestock-count',
        name: 'Contagem aérea de efetivos pecuários',
        category: 'service',
        priceCents: 30500,
        priceAkzCents: 25000000,
        priceEurCents: 27800,
        currency: 'USD',
        unit: 'operação',
        sectors: ['agro', 'livestock'],
        description:
            'Captura RGB ou térmica para apoio à contagem visual de animais e análise da distribuição do efetivo. Não substitui diagnóstico veterinário.',
        deliverables: [
          'Relatório de contagem',
          'Mapa de distribuição',
          'Evidências aéreas'
        ]),
    GvProduct(
        id: 'gps-collar',
        name: 'Colar GPS 4G para rastreio pecuário',
        category: 'hardware',
        priceCents: 28500,
        priceAkzCents: 23500000,
        priceEurCents: 26200,
        currency: 'USD',
        unit: 'unidade',
        featured: true,
        sectors: ['agro', 'livestock'],
        description:
            'Dispositivo GPS com SIM 4G, transmissão periódica, buffer offline e alertas de geofence na plataforma GeoVision. Plano de dados e cobertura são confirmados por local.',
        deliverables: [
          'Colar configurado',
          'Ativação no portal',
          'Configuração de geofence'
        ]),
    GvProduct(
        id: 'soil-iot-kit',
        name: 'Kit de sensores IoT de solo',
        category: 'hardware',
        priceCents: 32000,
        priceAkzCents: 26500000,
        priceEurCents: 29400,
        currency: 'USD',
        unit: 'kit',
        sectors: ['agro'],
        description:
            'Kit expandível para humidade, temperatura e parâmetros agronómicos compatíveis, com instalação e integração na plataforma. Disponibilidade depende do fornecedor certificado.',
        deliverables: [
          'Sensores e gateway',
          'Instalação inicial',
          'Dashboard e alertas'
        ]),
    GvProduct(
        id: 'weather-station',
        name: 'Estação meteorológica conectada',
        category: 'hardware',
        priceCents: 89000,
        priceAkzCents: 73500000,
        priceEurCents: 81900,
        currency: 'USD',
        unit: 'estação',
        sectors: ['agro', 'environment'],
        description:
            'Estação de campo para chuva, temperatura, humidade, vento e outros canais opcionais, integrada com alertas e histórico GeoVision. Solução expandível sujeita a levantamento de conectividade.',
        deliverables: [
          'Estação e gateway',
          'Instalação',
          'Integração de dados'
        ]),
    GvProduct(
        id: 'seed-certified-maize',
        name: 'Sementes certificadas — milho',
        category: 'seeds',
        priceCents: 17500,
        priceAkzCents: 14500000,
        priceEurCents: 16100,
        currency: 'USD',
        unit: 'saco',
        sectors: ['agro'],
        description:
            'Categoria de sementes certificadas para cotação conforme variedade, ciclo, região, lote e disponibilidade. A GeoVision confirma a especificação agronómica e o fornecedor antes da encomenda.',
        deliverables: [
          'Ficha do lote',
          'Certificação aplicável',
          'Rastreabilidade da entrega'
        ]),
    GvProduct(
        id: 'seed-reforestation',
        name: 'Mistura de sementes para reflorestação',
        category: 'seeds',
        priceCents: 12500,
        priceAkzCents: 10300000,
        priceEurCents: 11500,
        currency: 'USD',
        unit: 'lote',
        sectors: ['environment'],
        description:
            'Lote definido por projeto de recuperação vegetal, espécies autorizadas e condições locais. Pode ser associado ao serviço de dispersão aérea e monitorização NDVI.',
        deliverables: [
          'Especificação do lote',
          'Plano de dispersão',
          'Registo de rastreabilidade'
        ]),
    GvProduct(
        id: 'fertilizer',
        name: 'Fertilizantes e corretivos sob prescrição',
        category: 'inputs',
        priceCents: 3800,
        priceAkzCents: 3150000,
        priceEurCents: 3500,
        currency: 'USD',
        unit: 'saco',
        sectors: ['agro'],
        description:
            'Categoria para cotação de fertilizantes ou corretivos definidos por análise e prescrição agronómica. Formulação, dose e fornecedor são confirmados antes da venda.',
        deliverables: [
          'Ficha técnica',
          'Lote e validade',
          'Entrega rastreada'
        ]),
    GvProduct(
        id: 'mining-volume',
        name: 'Volumetria e stockpiles de mina',
        category: 'service',
        priceCents: 114500,
        priceAkzCents: 95000000,
        priceEurCents: 105500,
        currency: 'USD',
        unit: 'campanha',
        featured: true,
        sectors: ['mining'],
        description:
            'Levantamento RTK para cálculo comparativo de volumes de minério, estéril, cavas e stockpiles, com rastreabilidade por campanha.',
        deliverables: [
          'Modelo 3D',
          'Relatório volumétrico',
          'Ortomosaico e nuvem de pontos'
        ]),
    GvProduct(
        id: 'mining-topography',
        name: 'Topografia 3D de mina',
        category: 'service',
        priceCents: 150500,
        priceAkzCents: 125000000,
        priceEurCents: 138900,
        currency: 'USD',
        unit: 'projeto',
        sectors: ['mining'],
        description:
            'Mapeamento topográfico RTK por fotogrametria ou LiDAR quando contratado, preparado para engenharia, superfícies e cortes.',
        deliverables: [
          'DTM/DSM',
          'Curvas de nível',
          'Ortomosaico',
          'Relatório técnico'
        ]),
    GvProduct(
        id: 'mining-slopes',
        name: 'Monitorização de taludes',
        category: 'service',
        priceCents: 78500,
        priceAkzCents: 65000000,
        priceEurCents: 72200,
        currency: 'USD',
        unit: 'campanha',
        sectors: ['mining'],
        description:
            'Comparação de modelos de elevação e identificação de setores que requerem revisão geotécnica. Não substitui parecer de engenheiro geotécnico.',
        deliverables: [
          'Mapa de risco visual',
          'Análise de deformação',
          'Relatório de estabilidade'
        ]),
    GvProduct(
        id: 'construction-progress',
        name: 'Monitorização de progresso de obra',
        category: 'service',
        priceCents: 66500,
        priceAkzCents: 55000000,
        priceEurCents: 61100,
        currency: 'USD',
        unit: 'campanha',
        featured: true,
        sectors: ['construction'],
        description:
            'Campanhas recorrentes para documentar progresso, comparar planeado e executado e manter uma linha temporal visual para equipas e stakeholders.',
        deliverables: [
          'Ortomosaico',
          'Modelo 3D',
          'Relatório de progresso',
          'Timeline visual'
        ]),
    GvProduct(
        id: 'construction-earthworks',
        name: 'Volumetria de corte e aterro',
        category: 'service',
        priceCents: 90500,
        priceAkzCents: 75000000,
        priceEurCents: 83300,
        currency: 'USD',
        unit: 'projeto',
        sectors: ['construction', 'infrastructure'],
        description:
            'Medição de terraplenagem com comparação entre superfícies e documentação para controlo de obra.',
        deliverables: [
          'Relatório cut/fill',
          'Modelo 3D',
          'Comparação design vs. as-built'
        ]),
    GvProduct(
        id: 'infrastructure-inspection',
        name: 'Inspeção visual de infraestruturas',
        category: 'service',
        priceCents: 54500,
        priceAkzCents: 45000000,
        priceEurCents: 50000,
        currency: 'USD',
        unit: 'inspeção',
        sectors: ['infrastructure'],
        description:
            'Inspeção de pontes, estradas, barragens, linhas e estruturas com evidências georreferenciadas e priorização de pontos para revisão técnica.',
        deliverables: [
          'Relatório de inspeção',
          'Fotografias anotadas',
          'Mapa de pontos críticos'
        ]),
    GvProduct(
        id: 'infrastructure-corridor',
        name: 'Mapeamento de corredores e ativos lineares',
        category: 'service',
        priceCents: 144500,
        priceAkzCents: 120000000,
        priceEurCents: 133300,
        currency: 'USD',
        unit: 'projeto',
        sectors: ['infrastructure'],
        description:
            'Mapeamento linear de estradas, canais, pipelines ou linhas de transmissão, segmentado para comparação de condição e manutenção.',
        deliverables: [
          'Ortomosaico linear',
          'Perfil de elevação',
          'Análise por secção'
        ]),
    GvProduct(
        id: 'environment-baseline',
        name: 'Levantamento e baseline ambiental',
        category: 'service',
        priceCents: 78500,
        priceAkzCents: 65000000,
        priceEurCents: 72200,
        currency: 'USD',
        unit: 'projeto',
        sectors: ['environment'],
        description:
            'Mapeamento RGB, multiespectral e GIS de cobertura vegetal, corpos de água, áreas sensíveis e zonas de proteção para criar uma base comparável.',
        deliverables: [
          'Ortomosaico',
          'Mapa de cobertura',
          'Baseline e ficheiros GIS'
        ]),
    GvProduct(
        id: 'environment-reforestation',
        name: 'Dispersão aérea para reflorestação',
        category: 'service',
        priceCents: 72500,
        priceAkzCents: 60000000,
        priceEurCents: 66700,
        currency: 'USD',
        unit: 'operação',
        featured: true,
        sectors: ['environment'],
        description:
            'Planeamento e dispersão aérea de sementes com Agras T40 para recuperação vegetal, seguida de monitorização periódica. Espécies e plano ambiental requerem aprovação do projeto.',
        deliverables: [
          'Plano de cobertura',
          'Registo da dispersão',
          'Monitorização NDVI inicial'
        ]),
    GvProduct(
        id: 'hma-visual-support',
        name: 'Documentação aérea para programas HMA',
        category: 'service',
        priceCents: 66500,
        priceAkzCents: 55000000,
        priceEurCents: 61100,
        currency: 'USD',
        unit: 'campanha',
        sectors: ['environment'],
        description:
            'Suporte visual e GIS para delimitação, rotas de acesso, documentação de progresso e auditoria em programas de desminagem humanitária. Não deteta minas nem substitui equipas acreditadas.',
        deliverables: [
          'Ortomosaico HD',
          'Mapa de progresso',
          'Exportação GIS e relatório'
        ]),
    GvProduct(
        id: 'rtk-base',
        name: 'Solução RTK de campo',
        category: 'equipment',
        priceCents: 690000,
        priceAkzCents: 570000000,
        priceEurCents: 635000,
        currency: 'USD',
        unit: 'sistema',
        sectors: ['agro', 'mining', 'construction', 'infrastructure'],
        description:
            'Estação base RTK e configuração operacional para missões que requerem precisão centimétrica. O equipamento exato e a alternativa NTRIP são definidos após avaliação de cobertura.',
        deliverables: [
          'Hardware RTK',
          'Configuração',
          'Formação e verificação'
        ]),
    GvProduct(
        id: 'platform-pro',
        name: 'GeoVision Intelligence Pro',
        category: 'subscription',
        priceCents: 19900,
        priceAkzCents: 16500000,
        priceEurCents: 18300,
        currency: 'USD',
        unit: 'mês',
        sectors: [
          'agro',
          'mining',
          'construction',
          'infrastructure',
          'environment'
        ],
        description:
            'Acesso mensal a dashboards setoriais, mapas interativos, alertas, histórico, relatórios e suporte remoto. Operações de campo, hardware e processamento extraordinário são orçados separadamente.',
        deliverables: [
          'Portal e app móvel',
          'Alertas e dashboards',
          'Suporte remoto'
        ]),
  ];
}
