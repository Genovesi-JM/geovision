import '../../sites/domain/sector.dart';

class CustomerWorkspace {
  const CustomerWorkspace({
    required this.id,
    required this.organizationId,
    required this.name,
    required this.organizationName,
    required this.role,
    required this.sector,
    required this.sectors,
    required this.modulesEnabled,
  });

  final String id;
  final String organizationId;
  final String name;
  final String organizationName;
  final String role;
  final String sector;
  final List<String> sectors;
  final Set<String> modulesEnabled;

  factory CustomerWorkspace.fromJson(Map<String, dynamic> json) {
    var sectors = parseCanonicalSectorIds(json['sectors']);
    if (sectors.isEmpty) {
      sectors = parseCanonicalSectorIds(json['sector'] ?? json['sector_focus']);
    }
    return CustomerWorkspace(
      id: '${json['id'] ?? ''}',
      organizationId: '${json['organization_id'] ?? ''}',
      name: '${json['name'] ?? 'Workspace'}',
      organizationName:
          '${json['organization_name'] ?? json['org_name'] ?? ''}',
      role: '${json['role'] ?? 'viewer'}',
      sector: sectors.isEmpty ? '' : sectors.first,
      sectors: sectors,
      modulesEnabled: _strings(json['modules_enabled']).toSet(),
    );
  }
}

class CustomerExperience {
  const CustomerExperience({
    required this.activeWorkspaceId,
    required this.activeOrganizationId,
    required this.permissions,
    required this.capabilities,
    required this.workspaces,
  });

  final String? activeWorkspaceId;
  final String? activeOrganizationId;
  final Set<String> permissions;
  final Set<String> capabilities;
  final List<CustomerWorkspace> workspaces;

  CustomerWorkspace? get activeWorkspace {
    for (final workspace in workspaces) {
      if (workspace.id == activeWorkspaceId) return workspace;
    }
    return workspaces.isEmpty ? null : workspaces.first;
  }

  bool hasCapability(String capability) => capabilities.contains(capability);
  bool hasPermission(String permission) => permissions.contains(permission);

  factory CustomerExperience.fromJson(Map<String, dynamic> json) {
    final rawCapabilities = json['capabilities'];
    final capabilities = rawCapabilities is Map
        ? rawCapabilities.entries
            .where((entry) => entry.value == true)
            .map((entry) => entry.key.toString())
            .toSet()
        : _strings(rawCapabilities).toSet();
    final workspaces = (json['workspaces'] as List? ?? const [])
        .whereType<Map>()
        .map(
            (row) => CustomerWorkspace.fromJson(Map<String, dynamic>.from(row)))
        .where((workspace) => workspace.id.isNotEmpty)
        .toList();
    final activeId = json['active_workspace_id']?.toString();
    return CustomerExperience(
      activeWorkspaceId: activeId?.isNotEmpty == true
          ? activeId
          : (workspaces.isEmpty ? null : workspaces.first.id),
      activeOrganizationId: json['active_organization_id']?.toString(),
      permissions: _strings(json['permissions']).toSet(),
      capabilities: capabilities,
      workspaces: workspaces,
    );
  }

  static const demo = CustomerExperience(
    activeWorkspaceId: 'demo-workspace-spain-farm',
    activeOrganizationId: 'demo-organization',
    permissions: {
      'organization:read',
      'workspace:read',
      'workspace:contribute',
      'asset:read',
      'asset:create',
      'asset:update',
      'report:read',
      'billing:read',
    },
    capabilities: {
      'assets',
      'actions',
      'services',
      'reports',
      'devices',
      'team',
      'billing',
      'settings',
      'support',
    },
    workspaces: [
      CustomerWorkspace(
        id: 'demo-workspace-spain-farm',
        organizationId: 'demo-organization',
        name: 'Finca Madrid Norte',
        organizationName: 'GeoVision España Demo',
        role: 'owner',
        sector: 'agriculture',
        sectors: ['agriculture'],
        modulesEnabled: {'assets', 'actions', 'services', 'devices', 'reports'},
      ),
      CustomerWorkspace(
        id: 'demo-workspace-infrastructure',
        organizationId: 'demo-organization',
        name: 'Infraestructuras Madrid',
        organizationName: 'GeoVision España Demo',
        role: 'manager',
        sector: 'construction_infrastructure',
        sectors: ['construction_infrastructure'],
        modulesEnabled: {'assets', 'actions', 'services', 'reports'},
      ),
    ],
  );
}

List<String> _strings(dynamic value) => value is List
    ? value
        .map((item) => item.toString())
        .where((item) => item.isNotEmpty)
        .toList()
    : const [];
