import '../../../l10n/app_localizations.dart';

/// Localises a KPI label by its stable [definitionId], falling back to the
/// server-supplied [fallback] label for ids we don't have a translation for.
String localizedKpiLabel(
    AppLocalizations l10n, String definitionId, String fallback) {
  switch (definitionId) {
    case 'comfort_index':
      return l10n.kpiIndoorComfort;
    case 'air_quality':
      return l10n.kpiAirQuality;
    case 'energy_use':
      return l10n.kpiEnergyUse;
    case 'security_events':
      return l10n.kpiSecurityEvents;
    case 'ndvi_avg':
      return l10n.kpiNdviAvg;
    case 'ndre':
      return l10n.kpiNdre;
    case 'vegetation_coverage':
      return l10n.kpiVegetationCoverage;
    case 'water_stress':
      return l10n.kpiWaterStress;
    case 'infestation_risk':
      return l10n.kpiInfestationRisk;
    case 'anomaly_count':
      return l10n.kpiAnomalies;
    case 'cultivated_area':
      return l10n.kpiCultivatedArea;
    case 'chem_cost_ha':
      return l10n.kpiChemCostHa;
    case 'herd_count':
      return l10n.kpiHerdCount;
    case 'grazing_index':
      return l10n.kpiGrazingIndex;
    case 'water_points':
      return l10n.kpiWaterPointsOk;
    case 'defect_count':
      return l10n.kpiDefectsDetected;
    case 'thermal_anomaly':
      return l10n.kpiThermalAnomalies;
    default:
      return fallback;
  }
}
