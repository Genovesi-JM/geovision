/// Public onboarding profiles shared with the GeoVision website and API.
///
/// The API remains authoritative, but keeping these choices locally lets the
/// mobile wizard show only valid sectors and goals before submitting.
class AccountProfileDefinition {
  const AccountProfileDefinition({
    required this.id,
    required this.defaultSector,
    required this.allowedSectors,
    required this.defaultUseCases,
    required this.allowedUseCases,
    required this.isCompany,
  });

  final String id;
  final String defaultSector;
  final List<String> allowedSectors;
  final List<String> defaultUseCases;
  final List<String> allowedUseCases;
  final bool isCompany;
}

abstract final class AccountProfiles {
  static const public = <AccountProfileDefinition>[
    AccountProfileDefinition(
      id: 'farm',
      defaultSector: 'agriculture',
      allowedSectors: ['agriculture', 'environment'],
      defaultUseCases: ['soil', 'water', 'weather'],
      allowedUseCases: ['soil', 'irrigation', 'water', 'weather', 'livestock'],
      isCompany: false,
    ),
    AccountProfileDefinition(
      id: 'construction',
      defaultSector: 'construction_infrastructure',
      allowedSectors: ['construction_infrastructure', 'environment'],
      defaultUseCases: ['progress', 'site_environment'],
      allowedUseCases: [
        'progress',
        'inspections',
        'site_environment',
        'equipment'
      ],
      isCompany: true,
    ),
    AccountProfileDefinition(
      id: 'environment',
      defaultSector: 'environment',
      allowedSectors: ['environment'],
      defaultUseCases: ['air_quality', 'land_change'],
      allowedUseCases: [
        'air_quality',
        'water',
        'weather',
        'land_change',
        'inspections'
      ],
      isCompany: true,
    ),
    AccountProfileDefinition(
      id: 'industry',
      defaultSector: 'industry_energy_utilities',
      allowedSectors: [
        'industry_energy_utilities',
        'mining',
        'ports_logistics',
      ],
      defaultUseCases: ['site_environment', 'maintenance'],
      allowedUseCases: [
        'site_environment',
        'maintenance',
        'equipment',
        'inventory',
        'inspections'
      ],
      isCompany: true,
    ),
    AccountProfileDefinition(
      id: 'device',
      defaultSector: 'environment',
      allowedSectors: [
        'agriculture',
        'construction_infrastructure',
        'environment',
        'mining',
        'industry_energy_utilities',
        'ports_logistics'
      ],
      defaultUseCases: ['device_monitoring'],
      allowedUseCases: [
        'device_monitoring',
        'air_quality',
        'soil',
        'water',
        'weather',
        'equipment'
      ],
      isCompany: false,
    ),
    AccountProfileDefinition(
      id: 'enterprise',
      defaultSector: 'construction_infrastructure',
      allowedSectors: [
        'agriculture',
        'construction_infrastructure',
        'environment',
        'mining',
        'industry_energy_utilities',
        'ports_logistics'
      ],
      defaultUseCases: ['site_environment', 'maintenance'],
      allowedUseCases: [
        'soil',
        'irrigation',
        'water',
        'weather',
        'livestock',
        'comfort',
        'air_quality',
        'leaks',
        'progress',
        'inspections',
        'site_environment',
        'maintenance',
        'equipment',
        'security',
        'land_change',
        'inventory'
      ],
      isCompany: true,
    ),
  ];

  static AccountProfileDefinition byId(String id) => public.firstWhere(
        (profile) => profile.id == id,
        orElse: () => public[1],
      );
}
