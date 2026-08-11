/// Multi-sector model. Agriculture is the first complete workflow; the others
/// reuse the same components via sector-aware KPI definitions.
enum Sector { home, agriculture, livestock, infrastructure, mining, environment }

Sector sectorFromString(String v) {
  switch (v.toLowerCase()) {
    case 'home':
      return Sector.home;
    case 'agro':
      return Sector.agriculture;
    case 'livestock':
      return Sector.livestock;
    case 'infrastructure':
      return Sector.infrastructure;
    case 'mining':
      return Sector.mining;
    case 'environment':
      return Sector.environment;
    default:
      return Sector.agriculture;
  }
}

extension SectorX on Sector {
  String get id => name;
  String get label {
    switch (this) {
      case Sector.home:
        return 'Home';
      case Sector.agriculture:
        return 'Agriculture';
      case Sector.livestock:
        return 'Livestock';
      case Sector.infrastructure:
        return 'Infrastructure';
      case Sector.mining:
        return 'Mining';
      case Sector.environment:
        return 'Environment';
    }
  }
}
