import 'sector.dart';

/// Declarative, sector-aware KPI catalogue. Nothing about agriculture is
/// hard-coded into widgets — screens render whatever definitions apply to the
/// active sector, so new sectors are added by extending this catalogue only.
class KpiDefinition {
  const KpiDefinition({
    required this.id,
    required this.label,
    required this.unit,
    required this.sector,
    this.description,
    this.higherIsBetter = true,
  });

  final String id;
  final String label;
  final String unit;
  final Sector sector;
  final String? description;
  final bool higherIsBetter;
}

abstract final class KpiCatalogue {
  static const agriculture = <KpiDefinition>[
    KpiDefinition(
        id: 'ndvi_avg',
        label: 'Average NDVI',
        unit: '',
        sector: Sector.agro,
        description: 'Mean vegetation vigour across monitored fields.'),
    KpiDefinition(
        id: 'ndre',
        label: 'NDRE',
        unit: '',
        sector: Sector.agro,
        description: 'Red-edge index — nitrogen / canopy status.'),
    KpiDefinition(
        id: 'vegetation_coverage',
        label: 'Vegetation coverage',
        unit: '%',
        sector: Sector.agro),
    KpiDefinition(
        id: 'water_stress',
        label: 'Water stress',
        unit: '%',
        sector: Sector.agro,
        higherIsBetter: false),
    KpiDefinition(
        id: 'infestation_risk',
        label: 'Infestation risk',
        unit: '%',
        sector: Sector.agro,
        higherIsBetter: false),
    KpiDefinition(
        id: 'anomaly_count',
        label: 'Anomalies',
        unit: '',
        sector: Sector.agro,
        higherIsBetter: false),
    KpiDefinition(
        id: 'cultivated_area',
        label: 'Cultivated area',
        unit: 'ha',
        sector: Sector.agro),
    KpiDefinition(
        id: 'chem_cost_ha',
        label: 'Chemical cost / ha',
        unit: 'USD',
        sector: Sector.agro,
        higherIsBetter: false),
  ];

  static const infrastructure = <KpiDefinition>[
    KpiDefinition(
        id: 'defect_count',
        label: 'Defects detected',
        unit: '',
        sector: Sector.infrastructure,
        higherIsBetter: false),
    KpiDefinition(
        id: 'thermal_anomaly',
        label: 'Thermal anomalies',
        unit: '',
        sector: Sector.infrastructure,
        higherIsBetter: false),
  ];

  static List<KpiDefinition> forSector(Sector s) {
    switch (s) {
      case Sector.agro:
        return agriculture;
      case Sector.environment:
      case Sector.construction:
      case Sector.industry:
      case Sector.infrastructure:
        return infrastructure;
    }
  }
}
