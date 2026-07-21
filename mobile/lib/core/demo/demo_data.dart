import '../../features/alerts/domain/alert.dart';
import '../../features/devices/domain/device.dart';
import '../../features/orders/domain/product.dart';
import '../../features/reports/domain/report.dart';
import '../../features/sites/domain/sector.dart';
import '../../features/sites/domain/site.dart';
import '../../features/work/domain/service_request.dart';

/// Self-contained, clearly-labelled demo dataset. Lets the full app — every
/// navigation area and the primary agricultural workflow — run with zero
/// backend or provider credentials. Demo records are never mixed with
/// production data (they live only behind AppConfig.demoMode).
abstract final class DemoData {
  static const organisation = 'Fazenda Kilombo Agro';
  static const userEmail = 'demo@geovisionops.com';
  static const userName = 'Demo Operator';

  static DateTime _hAgo(int h) =>
      DateTime.now().toUtc().subtract(Duration(hours: h));
  static DateTime _dAgo(int d) =>
      DateTime.now().toUtc().subtract(Duration(days: d));

  static List<KpiValue> _agriKpis() => [
        KpiValue(
            definitionId: 'ndvi_avg',
            label: 'Average NDVI',
            value: 0.72,
            status: 'ok',
            trend: 'up',
            spark: const [0.61, 0.63, 0.66, 0.68, 0.70, 0.72],
            description: 'Healthy canopy vigour trending up after irrigation.',
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
            label: 'Vegetation coverage',
            value: 88,
            unit: '%',
            status: 'ok',
            trend: 'up',
            spark: const [80, 82, 84, 85, 87, 88],
            updatedAt: _hAgo(3)),
        KpiValue(
            definitionId: 'water_stress',
            label: 'Water stress',
            value: 23,
            unit: '%',
            status: 'warning',
            trend: 'up',
            spark: const [12, 14, 17, 19, 21, 23],
            description: 'Rising water stress in the south-east block.',
            updatedAt: _hAgo(3)),
        KpiValue(
            definitionId: 'infestation_risk',
            label: 'Infestation risk',
            value: 12,
            unit: '%',
            status: 'ok',
            trend: 'down',
            spark: const [22, 20, 17, 15, 13, 12],
            updatedAt: _hAgo(6)),
        KpiValue(
            definitionId: 'anomaly_count',
            label: 'Anomalies',
            value: 4,
            status: 'warning',
            trend: 'up',
            spark: const [1, 1, 2, 2, 3, 4],
            updatedAt: _hAgo(6)),
        KpiValue(
            definitionId: 'cultivated_area',
            label: 'Cultivated area',
            value: 142,
            unit: 'ha',
            status: 'ok',
            trend: 'stable',
            updatedAt: _dAgo(1)),
        KpiValue(
            definitionId: 'chem_cost_ha',
            label: 'Chemical cost / ha',
            value: 38,
            unit: 'USD',
            status: 'ok',
            trend: 'down',
            spark: const [46, 44, 43, 41, 39, 38],
            updatedAt: _dAgo(1)),
      ];

  static List<Site> sites() => [
        Site(
          id: 'site-1',
          name: 'Kilombo North Fields',
          sector: Sector.agriculture,
          status: SiteStatus.attention,
          location: 'Malanje, Angola',
          center: const GeoPoint(-9.5402, 16.3410),
          boundary: const [
            GeoPoint(-9.535, 16.336),
            GeoPoint(-9.535, 16.346),
            GeoPoint(-9.545, 16.346),
            GeoPoint(-9.545, 16.336),
          ],
          totalHectares: 142,
          openAlerts: 2,
          kpis: _agriKpis(),
          areas: [
            SiteArea(
                id: 'f1',
                name: 'Block A — Maize',
                hectares: 48,
                crop: 'Maize',
                kpis: _agriKpis().take(4).toList()),
            SiteArea(
                id: 'f2',
                name: 'Block B — Soybean',
                hectares: 54,
                crop: 'Soybean',
                kpis: _agriKpis().take(4).toList()),
            SiteArea(
                id: 'f3',
                name: 'Block C — Cassava',
                hectares: 40,
                crop: 'Cassava',
                kpis: _agriKpis().take(4).toList()),
          ],
        ),
        Site(
          id: 'site-2',
          name: 'Rio Verde Irrigation',
          sector: Sector.agriculture,
          status: SiteStatus.active,
          location: 'Huambo, Angola',
          center: const GeoPoint(-12.7761, 15.7392),
          totalHectares: 96,
          openAlerts: 0,
          kpis: _agriKpis(),
          areas: [
            SiteArea(
                id: 'f4',
                name: 'Pivot 1 — Wheat',
                hectares: 48,
                crop: 'Wheat',
                kpis: _agriKpis().take(3).toList()),
            SiteArea(
                id: 'f5',
                name: 'Pivot 2 — Potato',
                hectares: 48,
                crop: 'Potato',
                kpis: _agriKpis().take(3).toList()),
          ],
        ),
        const Site(
          id: 'site-3',
          name: 'Serra Livestock Range',
          sector: Sector.livestock,
          status: SiteStatus.active,
          location: 'Benguela, Angola',
          center: GeoPoint(-12.5763, 13.4055),
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
            title: 'Irrigation failure — Block A',
            description:
                'Soil moisture dropped 34% in 6h across the maize block; probable pump or valve failure.',
            siteId: 'site-1',
            location: 'Kilombo North · Block A',
            createdAt: _hAgo(2),
            recommendation: 'Dispatch a field technician to inspect the pump station and open a maintenance request.',
            lat: -9.537,
            lng: 16.340,
            evidence: const ['moisture_chart.png']),
        GvAlert(
            id: 'al-2',
            severity: 'medium',
            sector: 'agriculture',
            title: 'Rising water stress — south-east',
            description:
                'NDVI/thermal fusion indicates emerging water stress on ~6 ha.',
            siteId: 'site-1',
            location: 'Kilombo North',
            createdAt: _hAgo(9),
            recommendation:
                'Schedule an irrigation cycle within 48h and re-fly for confirmation.',
            lat: -9.543,
            lng: 16.344),
        GvAlert(
            id: 'al-3',
            severity: 'low',
            sector: 'livestock',
            title: 'GPS collar low battery',
            description: 'Collar #A17 battery at 14%.',
            siteId: 'site-3',
            location: 'Serra Range',
            createdAt: _dAgo(1),
            recommendation:
                'Replace or recharge the collar on next site visit.'),
        GvAlert(
            id: 'al-4',
            severity: 'information',
            sector: 'agriculture',
            title: 'New NDVI dataset available',
            description: 'Fresh multispectral survey processed for Rio Verde.',
            siteId: 'site-2',
            location: 'Rio Verde',
            createdAt: _dAgo(2)),
      ];

  static List<ServiceRequest> serviceRequests() => [
        ServiceRequest(
            id: 'sr-1',
            type: ServiceType.inspection.name,
            siteId: 'site-1',
            siteName: 'Kilombo North Fields',
            urgency: 'high',
            description: 'Post-alert inspection of Block A irrigation.',
            status: 'scheduled',
            createdAt: _hAgo(1),
            progressPercent: 20,
            assignedTeam: 'Field Team Malanje'),
        ServiceRequest(
            id: 'sr-2',
            type: ServiceType.droneOperation.name,
            siteId: 'site-2',
            siteName: 'Rio Verde Irrigation',
            urgency: 'normal',
            description: 'Monthly multispectral survey.',
            status: 'completed',
            createdAt: _dAgo(6),
            progressPercent: 100,
            assignedTeam: 'UAV Team 2'),
      ];

  static List<GvReport> reports() => [
        GvReport(
            id: 'rp-1',
            title: 'NDVI Health Report — Kilombo North',
            siteName: 'Kilombo North Fields',
            type: 'ndvi',
            createdAt: _dAgo(1),
            sizeBytes: 2_400_000),
        GvReport(
            id: 'rp-2',
            title: 'Irrigation Inspection — Rio Verde',
            siteName: 'Rio Verde Irrigation',
            type: 'inspection',
            createdAt: _dAgo(7),
            sizeBytes: 5_100_000),
        GvReport(
            id: 'rp-3',
            title: 'Thermal Survey Summary',
            siteName: 'Kilombo North Fields',
            type: 'thermal',
            createdAt: _dAgo(14),
            sizeBytes: 3_300_000),
      ];

  static List<GvDevice> devices() => [
        GvDevice(
            id: 'dv-1',
            name: 'Soil NPK Sensor A',
            type: 'soil_sensor',
            siteName: 'Kilombo North',
            status: 'online',
            batteryPercent: 82,
            signalPercent: 74,
            lastReadingAt: _hAgo(1),
            lastReadingLabel: 'N 42 · P 18 · K 55 mg/kg',
            lastMaintenanceAt: _dAgo(30)),
        GvDevice(
            id: 'dv-2',
            name: 'Weather Station 1',
            type: 'weather_station',
            siteName: 'Kilombo North',
            status: 'online',
            batteryPercent: 91,
            signalPercent: 88,
            lastReadingAt: _hAgo(1),
            lastReadingLabel: '27°C · 61% RH · 8 km/h',
            lastMaintenanceAt: _dAgo(45)),
        GvDevice(
            id: 'dv-3',
            name: 'Soil Moisture Probe SE',
            type: 'soil_sensor',
            siteName: 'Kilombo North',
            status: 'offline',
            batteryPercent: 12,
            signalPercent: 0,
            lastReadingAt: _hAgo(7),
            lastReadingLabel: '18% VWC',
            lastMaintenanceAt: _dAgo(60)),
        GvDevice(
            id: 'dv-4',
            name: 'GPS Collar A17',
            type: 'gps_collar',
            siteName: 'Serra Range',
            status: 'maintenance',
            batteryPercent: 14,
            signalPercent: 40,
            lastReadingAt: _hAgo(4),
            lastMaintenanceAt: _dAgo(90)),
      ];

  static List<GvProduct> products() => const [
        GvProduct(
            id: 'pr-1',
            name: 'Multispectral Drone Survey',
            category: 'service',
            priceCents: 45000,
            currency: 'USD',
            description: 'Per-flight NDVI/NDRE survey up to 150 ha.',
            unit: 'flight'),
        GvProduct(
            id: 'pr-2',
            name: 'Soil NPK Sensor Kit',
            category: 'hardware',
            priceCents: 32000,
            currency: 'USD',
            description: 'IoT soil sensor with installation.',
            unit: 'unit'),
        GvProduct(
            id: 'pr-3',
            name: 'Monitoring — Pro (monthly)',
            category: 'subscription',
            priceCents: 19900,
            currency: 'USD',
            description: 'Continuous alerts, dashboards and monthly reports.',
            unit: 'month'),
        GvProduct(
            id: 'pr-4',
            name: 'Thermal Infrastructure Inspection',
            category: 'service',
            priceCents: 60000,
            currency: 'USD',
            description: 'Thermal + RGB inspection with defect report.',
            unit: 'job'),
      ];

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
      ];
}
