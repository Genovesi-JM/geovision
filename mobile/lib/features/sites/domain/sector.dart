/// Canonical public sector identifiers shared by onboarding, sites and store.
abstract final class PublicSectorIds {
  static const agriculture = 'agriculture';
  static const constructionInfrastructure = 'construction_infrastructure';
  static const environment = 'environment';
  static const mining = 'mining';
  static const industryEnergyUtilities = 'industry_energy_utilities';
  static const portsLogistics = 'ports_logistics';

  static const values = <String>[
    agriculture,
    constructionInfrastructure,
    environment,
    mining,
    industryEnergyUtilities,
    portsLogistics,
  ];
}

enum Sector {
  agriculture,
  constructionInfrastructure,
  environment,
  mining,
  industryEnergyUtilities,
  portsLogistics,
}

String _sectorKey(String value) => value
    .trim()
    .toLowerCase()
    .replaceAll(RegExp('[áàâãä]'), 'a')
    .replaceAll(RegExp('[éèêë]'), 'e')
    .replaceAll(RegExp('[íìîï]'), 'i')
    .replaceAll(RegExp('[óòôõö]'), 'o')
    .replaceAll(RegExp('[úùûü]'), 'u')
    .replaceAll('ç', 'c')
    .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
    .replaceAll(RegExp(r'^_+|_+$'), '');

String canonicalSectorId(String value) {
  final key = _sectorKey(value);
  switch (key) {
    case 'agro':
    case 'agropecuaria':
    case 'agriculture':
    case 'agricultura':
    case 'agricultura_e_pecuaria':
    case 'livestock':
    case 'agriculture_livestock':
    case 'agricultura_pecuaria':
      return PublicSectorIds.agriculture;
    case 'construction':
    case 'infrastructure':
    case 'construction_infrastructure':
    case 'construction_and_infrastructure':
    case 'construcao_e_infraestruturas':
    case 'construcao_infraestrutura':
    case 'construcao_infraestruturas':
    case 'infrastructures':
      return PublicSectorIds.constructionInfrastructure;
    case 'ambiente':
    case 'ambiental':
    case 'environmental':
    case 'environment':
      return PublicSectorIds.environment;
    case 'mining':
    case 'mine':
    case 'mines':
    case 'mineracao':
    case 'quarry':
      return PublicSectorIds.mining;
    case 'industry':
    case 'industrial':
    case 'industria':
    case 'energia':
    case 'energy':
    case 'utilities':
    case 'solar':
    case 'industry_energy':
    case 'industria_e_energia_utilities':
    case 'industria_energia_e_utilities':
    case 'industria_energia_utilities':
    case 'industry_energy_utilities':
      return PublicSectorIds.industryEnergyUtilities;
    case 'port':
    case 'portos':
    case 'ports':
    case 'logistics':
    case 'logistica':
    case 'portos_logistica':
    case 'portos_e_logistica':
    case 'ports_and_logistics':
    case 'ports_industrial':
    case 'ports_logistics':
      return PublicSectorIds.portsLogistics;
    default:
      return key;
  }
}

/// Parses either a JSON list or a legacy comma-separated sector field.
///
/// Matching is greedy so the known label "Indústria, Energia & Utilities"
/// remains one sector even when it appears inside an unquoted CSV value.
List<String> parseCanonicalSectorIds(dynamic value) {
  final inputs = value is List
      ? value.map((item) => item.toString())
      : value is String
          ? <String>[value]
          : const <String>[];
  final parsed = <String>[];
  for (final input in inputs) {
    final parts = input
        .split(',')
        .map((part) => part.trim())
        .where((part) => part.isNotEmpty)
        .toList();
    var index = 0;
    while (index < parts.length) {
      String? match;
      var nextIndex = index + 1;
      for (var end = parts.length; end > index; end -= 1) {
        final candidate = parts.sublist(index, end).join(', ');
        final canonical = canonicalSectorId(candidate);
        if (PublicSectorIds.values.contains(canonical)) {
          match = canonical;
          nextIndex = end;
          break;
        }
      }
      if (match != null && !parsed.contains(match)) parsed.add(match);
      index = nextIndex;
    }
  }
  return parsed;
}

Sector sectorFromString(String value) {
  final canonical = canonicalSectorId(value);
  return switch (canonical) {
    PublicSectorIds.agriculture => Sector.agriculture,
    PublicSectorIds.constructionInfrastructure =>
      Sector.constructionInfrastructure,
    PublicSectorIds.environment => Sector.environment,
    PublicSectorIds.mining => Sector.mining,
    PublicSectorIds.industryEnergyUtilities => Sector.industryEnergyUtilities,
    PublicSectorIds.portsLogistics => Sector.portsLogistics,
    _ => throw FormatException('Unknown GeoVision sector: $value'),
  };
}

extension SectorX on Sector {
  String get id => switch (this) {
        Sector.agriculture => PublicSectorIds.agriculture,
        Sector.constructionInfrastructure =>
          PublicSectorIds.constructionInfrastructure,
        Sector.environment => PublicSectorIds.environment,
        Sector.mining => PublicSectorIds.mining,
        Sector.industryEnergyUtilities =>
          PublicSectorIds.industryEnergyUtilities,
        Sector.portsLogistics => PublicSectorIds.portsLogistics,
      };

  String get label {
    switch (this) {
      case Sector.agriculture:
        return 'Agricultura & Pecuária';
      case Sector.constructionInfrastructure:
        return 'Construção & Infraestruturas';
      case Sector.environment:
        return 'Ambiente';
      case Sector.mining:
        return 'Mineração';
      case Sector.industryEnergyUtilities:
        return 'Indústria, Energia & Utilities';
      case Sector.portsLogistics:
        return 'Portos & Logística';
    }
  }
}
