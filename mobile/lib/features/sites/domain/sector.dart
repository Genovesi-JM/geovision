/// Canonical public sectors shared by account onboarding, sites and the store.
/// Older API values are normalized in [sectorFromString].
enum Sector { agro, environment, construction, industry, infrastructure }

Sector sectorFromString(String v) {
  switch (v.toLowerCase()) {
    case 'agro':
    case 'agriculture':
    case 'livestock':
      return Sector.agro;
    case 'infrastructure':
      return Sector.infrastructure;
    case 'mining':
    case 'industry':
      return Sector.industry;
    case 'construction':
      return Sector.construction;
    case 'ambiental':
    case 'environment':
      return Sector.environment;
    default:
      return Sector.infrastructure;
  }
}

extension SectorX on Sector {
  String get id => name;
  String get label {
    switch (this) {
      case Sector.agro:
        return 'Agriculture & livestock';
      case Sector.environment:
        return 'Environment';
      case Sector.construction:
        return 'Construction';
      case Sector.industry:
        return 'Industry & mining';
      case Sector.infrastructure:
        return 'Infrastructure';
    }
  }
}
