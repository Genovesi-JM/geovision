import '../../features/alerts/domain/alert.dart';
import '../../features/devices/domain/device.dart';
import '../../features/orders/domain/product.dart';
import '../../features/orders/data/demo_store_catalog.dart';
import '../../features/reports/domain/report.dart';
import '../../features/sites/domain/sector.dart';
import '../../features/sites/domain/site.dart';
import '../../features/work/domain/service_request.dart';

/// Self-contained, clearly-labelled demo dataset. Lets the full app — every
/// navigation area and the primary agricultural workflow — run with zero
/// backend or provider credentials. Demo records are never mixed with
/// production data (they live only behind AppConfig.demoMode).
abstract final class DemoData {
  static const organisation = 'GeoVision España Demo';
  static const userEmail = 'demo@geovisionops.com';
  static const userName = 'Demo Operator';

  static DateTime _hAgo(int h) =>
      DateTime.now().toUtc().subtract(Duration(hours: h));
  static DateTime _dAgo(int d) =>
      DateTime.now().toUtc().subtract(Duration(days: d));

  static List<KpiValue> _agriKpis() => [
        KpiValue(
            definitionId: 'ndvi_avg',
            label: 'NDVI medio',
            value: 0.72,
            status: 'ok',
            trend: 'up',
            spark: const [0.61, 0.63, 0.66, 0.68, 0.70, 0.72],
            description: 'El vigor de la cubierta mejora tras el riego.',
            updatedAt: _hAgo(3)),
        KpiValue(
            definitionId: 'ndre',
            label: 'NDRE',
            value: 0.41,
            status: 'ok',
            trend: 'stable',
            spark: const [0.39, 0.40, 0.40, 0.41, 0.41, 0.41],
            updatedAt: _hAgo(3)),
        KpiValue(
            definitionId: 'vegetation_coverage',
            label: 'Cobertura vegetal',
            value: 88,
            unit: '%',
            status: 'ok',
            trend: 'up',
            spark: const [80, 82, 84, 85, 87, 88],
            updatedAt: _hAgo(3)),
        KpiValue(
            definitionId: 'water_stress',
            label: 'Estrés hídrico',
            value: 23,
            unit: '%',
            status: 'warning',
            trend: 'up',
            spark: const [12, 14, 17, 19, 21, 23],
            description: 'Aumenta el estrés hídrico en el bloque sureste.',
            updatedAt: _hAgo(3)),
        KpiValue(
            definitionId: 'infestation_risk',
            label: 'Riesgo de plaga',
            value: 12,
            unit: '%',
            status: 'ok',
            trend: 'down',
            spark: const [22, 20, 17, 15, 13, 12],
            updatedAt: _hAgo(6)),
        KpiValue(
            definitionId: 'anomaly_count',
            label: 'Anomalías',
            value: 4,
            status: 'warning',
            trend: 'up',
            spark: const [1, 1, 2, 2, 3, 4],
            updatedAt: _hAgo(6)),
        KpiValue(
            definitionId: 'cultivated_area',
            label: 'Superficie cultivada',
            value: 142,
            unit: 'ha',
            status: 'ok',
            trend: 'stable',
            updatedAt: _dAgo(1)),
        KpiValue(
            definitionId: 'chem_cost_ha',
            label: 'Coste de insumos / ha',
            value: 38,
            unit: 'EUR',
            status: 'ok',
            trend: 'down',
            spark: const [46, 44, 43, 41, 39, 38],
            updatedAt: _dAgo(1)),
      ];

  static List<Site> sites() => [
        Site(
          id: 'site-1',
          name: 'Finca Madrid Norte',
          sector: Sector.agriculture,
          status: SiteStatus.attention,
          location: 'Comunidad de Madrid, España',
          center: const GeoPoint(40.55, -3.65),
          boundary: const [
            GeoPoint(40.555, -3.656),
            GeoPoint(40.555, -3.644),
            GeoPoint(40.545, -3.644),
            GeoPoint(40.545, -3.656),
          ],
          totalHectares: 142,
          openAlerts: 2,
          kpis: _agriKpis(),
          areas: [
            SiteArea(
                id: 'f1',
                name: 'Bloque A — Maíz',
                hectares: 48,
                crop: 'Maíz',
                kpis: _agriKpis().take(4).toList()),
            SiteArea(
                id: 'f2',
                name: 'Bloque B — Soja',
                hectares: 54,
                crop: 'Soja',
                kpis: _agriKpis().take(4).toList()),
            SiteArea(
                id: 'f3',
                name: 'Bloque C — Girasol',
                hectares: 40,
                crop: 'Girasol',
                kpis: _agriKpis().take(4).toList()),
          ],
        ),
        Site(
          id: 'site-2',
          name: 'Regadío del Ebro',
          sector: Sector.agriculture,
          status: SiteStatus.active,
          location: 'Zaragoza, España',
          center: const GeoPoint(41.6488, -0.8891),
          totalHectares: 96,
          openAlerts: 0,
          kpis: _agriKpis(),
          areas: [
            SiteArea(
                id: 'f4',
                name: 'Pívot 1 — Trigo',
                hectares: 48,
                crop: 'Trigo',
                kpis: _agriKpis().take(3).toList()),
            SiteArea(
                id: 'f5',
                name: 'Pívot 2 — Patata',
                hectares: 48,
                crop: 'Patata',
                kpis: _agriKpis().take(3).toList()),
          ],
        ),
        const Site(
          id: 'site-3',
          name: 'Dehesa Salamanca',
          sector: Sector.agriculture,
          status: SiteStatus.active,
          location: 'Castilla y León, España',
          center: GeoPoint(40.9701, -5.6635),
          totalHectares: 320,
          openAlerts: 1,
          kpis: [],
          areas: [],
        ),
      ];

  static List<GvAlert> alerts() => [
        GvAlert(
            id: 'al-1',
            severity: 'critical',
            sector: 'agriculture',
            title: 'Fallo de riego — Bloque A',
            description:
                'La humedad del suelo cayó un 34% en 6 h en el bloque de maíz; posible fallo de bomba o válvula.',
            siteId: 'site-1',
            location: 'Finca Madrid Norte · Block A',
            createdAt: _hAgo(2),
            recommendation: 'Enviar un técnico de campo para inspeccionar la estación de bombeo y abrir una solicitud de mantenimiento.',
            lat: 40.553,
            lng: -3.650,
            evidence: const ['moisture_chart.png']),
        GvAlert(
            id: 'al-2',
            severity: 'medium',
            sector: 'agriculture',
            title: 'Aumento del estrés hídrico — sureste',
            description:
                'La fusión NDVI/térmica indica estrés hídrico emergente en unas 6 ha.',
            siteId: 'site-1',
            location: 'Finca Madrid Norte',
            createdAt: _hAgo(9),
            recommendation:
                'Programar un ciclo de riego en 48 h y repetir el vuelo para confirmarlo.',
            lat: 40.547,
            lng: -3.646),
        GvAlert(
            id: 'al-3',
            severity: 'low',
            sector: 'livestock',
            title: 'Batería baja en collar GPS',
            description: 'La batería del collar A17 está al 14%.',
            siteId: 'site-3',
            location: 'Dehesa Salamanca',
            createdAt: _dAgo(1),
            recommendation:
                'Sustituir o recargar el collar en la próxima visita.'),
        GvAlert(
            id: 'al-4',
            severity: 'information',
            sector: 'agriculture',
            title: 'Nuevo conjunto NDVI disponible',
            description:
                'Nuevo vuelo multiespectral procesado para Regadío del Ebro.',
            siteId: 'site-2',
            location: 'Regadío del Ebro',
            createdAt: _dAgo(2)),
      ];

  static List<ServiceRequest> serviceRequests() => [
        ServiceRequest(
            id: 'sr-1',
            type: ServiceType.inspection.name,
            siteId: 'site-1',
            siteName: 'Finca Madrid Norte',
            urgency: 'high',
            description: 'Inspección del riego del Bloque A tras la alerta.',
            status: 'scheduled',
            createdAt: _hAgo(1),
            progressPercent: 20,
            assignedTeam: 'Equipo de campo Madrid'),
        ServiceRequest(
            id: 'sr-2',
            type: ServiceType.droneOperation.name,
            siteId: 'site-2',
            siteName: 'Regadío del Ebro',
            urgency: 'normal',
            description: 'Levantamiento multiespectral mensual.',
            status: 'completed',
            createdAt: _dAgo(6),
            progressPercent: 100,
            assignedTeam: 'UAV Team 2'),
      ];

  static List<GvReport> reports() => [
        GvReport(
            id: 'rp-1',
            title: 'Informe de salud NDVI — Finca Madrid Norte',
            siteName: 'Finca Madrid Norte',
            type: 'ndvi',
            createdAt: _dAgo(1),
            sizeBytes: 2_400_000),
        GvReport(
            id: 'rp-2',
            title: 'Inspección de riego — Regadío del Ebro',
            siteName: 'Regadío del Ebro',
            type: 'inspection',
            createdAt: _dAgo(7),
            sizeBytes: 5_100_000),
        GvReport(
            id: 'rp-3',
            title: 'Resumen del estudio térmico',
            siteName: 'Finca Madrid Norte',
            type: 'thermal',
            createdAt: _dAgo(14),
            sizeBytes: 3_300_000),
      ];

  static List<GvDevice> devices() => [
        GvDevice(
            id: 'dv-1',
            name: 'Soil NPK Sensor A',
            type: 'soil_sensor',
            siteName: 'Finca Madrid Norte',
            status: 'online',
            batteryPercent: 82,
            signalPercent: 74,
            providerId: 'geovision-mqtt',
            transport: 'mqtt',
            capabilities: const ['telemetry', 'alerts', 'calibration'],
            lastReadingAt: _hAgo(1),
            lastReadingLabel: 'N 42 · P 18 · K 55 mg/kg',
            lastMaintenanceAt: _dAgo(30)),
        GvDevice(
            id: 'dv-2',
            name: 'Weather Station 1',
            type: 'weather_station',
            siteName: 'Finca Madrid Norte',
            status: 'online',
            batteryPercent: 91,
            signalPercent: 88,
            providerId: 'weather-api-bridge',
            transport: 'api',
            capabilities: const ['telemetry', 'forecast', 'alerts'],
            lastReadingAt: _hAgo(1),
            lastReadingLabel: '27°C · 61% RH · 8 km/h',
            lastMaintenanceAt: _dAgo(45)),
        GvDevice(
            id: 'dv-3',
            name: 'Soil Moisture Probe SE',
            type: 'soil_sensor',
            siteName: 'Finca Madrid Norte',
            status: 'offline',
            batteryPercent: 12,
            signalPercent: 0,
            providerId: 'geovision-lorawan',
            transport: 'lorawan',
            capabilities: const ['telemetry', 'alerts'],
            integrationMessage: 'Sem heartbeat recente; dados em cache.',
            lastReadingAt: _hAgo(7),
            lastReadingLabel: '18% VWC',
            lastMaintenanceAt: _dAgo(60)),
        GvDevice(
            id: 'dv-4',
            name: 'GPS Collar A17',
            type: 'gps_collar',
            siteName: 'Dehesa Salamanca',
            status: 'maintenance',
            batteryPercent: 14,
            signalPercent: 40,
            providerId: 'gps-4g-vendor',
            transport: 'api',
            capabilities: const ['location', 'geofence', 'history'],
            lastReadingAt: _hAgo(4),
            lastMaintenanceAt: _dAgo(90)),
        const GvDevice(
            id: 'dv-5',
            name: 'Sensor de humidade novo',
            type: 'soil_sensor',
            siteName: 'Regadío del Ebro',
            status: 'pairing',
            batteryPercent: 100,
            signalPercent: 65,
            providerId: 'ble-provisioning',
            transport: 'ble',
            capabilities: ['provisioning', 'telemetry'],
            integrationMessage:
                'A aguardar permissão Bluetooth e configuração.'),
        const GvDevice(
            id: 'dv-6',
            name: 'Gateway estrutural Modbus',
            type: 'structural_gateway',
            siteName: 'Madrid M-30 — Tramo 4',
            status: 'credentials_required',
            batteryPercent: 100,
            signalPercent: 72,
            providerId: 'vendor-modbus-cloud',
            transport: 'modbus_gateway',
            capabilities: ['vibration', 'tilt', 'alerts'],
            integrationMessage: 'Credenciais sandbox do fabricante em falta.'),
        const GvDevice(
            id: 'dv-7',
            name: 'Controlador proprietário legado',
            type: 'legacy_controller',
            siteName: 'Finca Madrid Norte',
            status: 'unsupported',
            batteryPercent: 0,
            signalPercent: 0,
            providerId: 'none',
            transport: 'unknown',
            integrationMessage:
                'Sem API ou protocolo documentado; requer gateway compatível.'),
        const GvDevice(
            id: 'dv-8',
            name: 'Gateway LoRa da exploração',
            type: 'gateway',
            siteName: 'Finca Madrid Norte',
            status: 'error',
            batteryPercent: 100,
            signalPercent: 55,
            providerId: 'lorawan-network-server',
            transport: 'lorawan',
            capabilities: ['telemetry', 'device_management'],
            integrationMessage:
                'Erro de rota para o servidor de rede; repetível.'),
      ];

  static List<GvProduct> products() => DemoStoreCatalog.products;

  /* Legacy inline catalogue retained below for migration reference.
  static List<GvProduct> legacyProducts() => const [
        GvProduct(
            id: 'seed-maize-1',
            name: 'Sementes de milho GV 28810 PRO3',
            category: 'seeds',
            priceCents: 17500,
            currency: 'EUR',
            description:
                'Híbrido de ciclo médio desenvolvido para clima tropical. Boa tolerância ao calor, estabilidade de espiga e elevado potencial produtivo quando combinado com adubação equilibrada. Saco selado com lote e rastreabilidade; recomendação agronómica disponível antes da compra.',
            unit: 'saco',
            featured: true),
        GvProduct(
            id: 'seed-soy-1',
            name: 'Sementes de soja GV 8080 PRO',
            category: 'seeds',
            priceCents: 9650,
            currency: 'EUR',
            description:
                'Semente certificada de soja com germinação uniforme e vigor inicial elevado. Indicada para produtores que procuram um estabelecimento de cultura consistente, com informação de lote, validade e orientação técnica de sementeira.',
            unit: 'saco'),
        GvProduct(
            id: 'input-fertilizer-1',
            name: 'Fertilizante NPK 20-10-20',
            category: 'inputs',
            priceCents: 3800,
            currency: 'EUR',
            description:
                'Formulação granulada NPK para nutrição equilibrada e distribuição homogénea no campo. Adequada a planos de fertilização orientados por análise de solo; a dose final deve ser validada por um técnico agrónomo.',
            unit: 'saco'),
        GvProduct(
            id: 'pr-1',
            name: 'Levantamento multiespectral por drone',
            category: 'service',
            priceCents: 45000,
            currency: 'USD',
            description:
                'Operação de campo até 150 ha com captura RGB e multiespectral, processamento NDVI/NDRE, identificação de zonas de stress e entrega de mapa, relatório técnico e recomendações prioritárias.',
            unit: 'operação'),
        GvProduct(
            id: 'pr-2',
            name: 'Kit sensor de solo GV Soil Pro',
            category: 'hardware',
            priceCents: 32000,
            currency: 'USD',
            description:
                'Kit IoT para monitorização de humidade, temperatura e indicadores de fertilidade do solo. Inclui gateway, instalação inicial, calibração e ligação ao painel GeoVision para alertas e histórico.',
            unit: 'unidade',
            featured: true),
        GvProduct(
            id: 'pr-tractor',
            name: 'Trator agrícola GV 120',
            category: 'equipment',
            priceCents: 12900000,
            currency: 'USD',
            description:
                'Trator agrícola de 120 cv para preparação de solo, sementeira e transporte. Cabina ergonómica, tomada de força, engate de três pontos e preparação para telemetria GeoVision. Entrega técnica e formação do operador sob consulta.',
            unit: 'unidade'),
        GvProduct(
            id: 'pr-sprayer',
            name: 'Pulverizador inteligente 3000',
            category: 'equipment',
            priceCents: 1890000,
            currency: 'USD',
            description:
                'Pulverizador de precisão com controlo independente de secções, regulação eletrónica de caudal e registo da aplicação. Reduz sobreposições e permite documentar cada intervenção no historial da exploração.',
            unit: 'unidade'),
        GvProduct(
            id: 'pr-drone',
            name: 'Drone agrícola GeoVision A20',
            category: 'equipment',
            priceCents: 2150000,
            currency: 'USD',
            description:
                'Plataforma aérea para pulverização e distribuição de precisão, com planeamento de rotas, controlo de caudal e registo operacional. A proposta comercial inclui avaliação da propriedade, configuração e formação; utilização sujeita à regulamentação aplicável.',
            unit: 'unidade',
            featured: true),
        GvProduct(
            id: 'pr-3',
            name: 'Monitorização GeoVision Pro',
            category: 'subscription',
            priceCents: 19900,
            currency: 'USD',
            description:
                'Plano mensal com dashboards, alertas operacionais, consolidação de dados IoT e relatório de desempenho. Inclui acompanhamento remoto e prioridade no suporte; equipamentos e operações de campo são orçados separadamente.',
            unit: 'mês'),
        GvProduct(
            id: 'pr-4',
            name: 'Inspeção térmica de infraestruturas',
            category: 'service',
            priceCents: 60000,
            currency: 'USD',
            description:
                'Inspeção combinada RGB e termográfica para localizar aquecimento anómalo, infiltrações e defeitos visíveis. Entrega evidências georreferenciadas, classificação de prioridade e relatório técnico para planeamento de manutenção.',
            unit: 'serviço'),
      ]; */

  static List<GvOrder> orders() => [
        GvOrder(
            id: 'or-1',
            createdAt: _dAgo(10),
            totalCents: 45000,
            currency: 'USD',
            status: 'fulfilled',
            paymentStatus: 'paid',
            items: const ['Multispectral Drone Survey']),
        GvOrder(
            id: 'or-2',
            createdAt: _dAgo(2),
            totalCents: 19900,
            currency: 'USD',
            status: 'confirmed',
            paymentStatus: 'pending',
            items: const ['Monitoring — Pro (monthly)']),
        GvOrder(
            id: 'GV-2405-0187',
            createdAt: _dAgo(1),
            totalCents: 54245,
            currency: 'USD',
            status: 'in_transit',
            paymentStatus: 'paid',
            items: const [
              'Sementes de milho',
              'Sensor de solo',
              'Fertilizante NPK'
            ],
            delivery: GvDelivery(
              trackingCode: 'GV-2405-0187',
              status: 'Em trânsito',
              destination: 'Finca Madrid Norte, Madrid, España',
              estimatedArrival:
                  DateTime.now().toUtc().add(const Duration(days: 3)),
              progress: .68,
              vehicleLatitude: 40.49,
              vehicleLongitude: -3.70,
            )),
      ];
}
