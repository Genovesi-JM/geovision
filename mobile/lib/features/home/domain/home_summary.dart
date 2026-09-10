import '../../../core/routing/customer_routes.dart';

class HomeAttention {
  const HomeAttention({
    required this.critical,
    required this.attention,
    required this.scheduled,
    required this.completedRecent,
    required this.activeServices,
    required this.offlineDevices,
  });

  final int critical;
  final int attention;
  final int scheduled;
  final int completedRecent;
  final int activeServices;
  final int offlineDevices;

  int get needsAttention => critical + attention;

  factory HomeAttention.fromJson(Map<String, dynamic> json) => HomeAttention(
        critical: _integer(json['critical'] ?? json['critical_actions']),
        attention: _integer(json['attention'] ?? json['attention_actions']),
        scheduled: _integer(json['scheduled'] ?? json['scheduled_actions']),
        completedRecent:
            _integer(json['completed_recent'] ?? json['completed_actions']),
        activeServices: _integer(json['active_services']),
        offlineDevices: _integer(json['offline_devices']),
      );
}

class HomePriorityItem {
  const HomePriorityItem({
    required this.id,
    required this.targetType,
    required this.targetId,
    required this.title,
    required this.summary,
    required this.severity,
    this.dueAt,
  });

  final String id;
  final String targetType;
  final String targetId;
  final String title;
  final String summary;
  final String severity;
  final DateTime? dueAt;

  String? get appPath => CustomerRoutes.forTarget(targetType, targetId);

  factory HomePriorityItem.fromJson(Map<String, dynamic> json) =>
      HomePriorityItem(
        id: '${json['id'] ?? ''}',
        targetType: '${json['target_type'] ?? ''}'.toUpperCase(),
        targetId: '${json['target_id'] ?? ''}',
        title: '${json['title'] ?? ''}',
        summary: '${json['summary'] ?? ''}',
        severity: '${json['severity'] ?? 'attention'}'.toLowerCase(),
        dueAt: DateTime.tryParse('${json['due_at'] ?? ''}'),
      );
}

class HomeResult {
  const HomeResult({
    required this.targetType,
    required this.targetId,
    required this.title,
    required this.summary,
    this.completedAt,
  });

  final String targetType;
  final String targetId;
  final String title;
  final String summary;
  final DateTime? completedAt;

  String? get appPath => CustomerRoutes.forTarget(targetType, targetId);

  factory HomeResult.fromJson(Map<String, dynamic> json) => HomeResult(
        targetType: '${json['target_type'] ?? ''}'.toUpperCase(),
        targetId: '${json['target_id'] ?? ''}',
        title: '${json['title'] ?? ''}',
        summary: '${json['summary'] ?? ''}',
        completedAt: DateTime.tryParse('${json['completed_at'] ?? ''}'),
      );
}

class HomeSummary {
  const HomeSummary({
    required this.workspaceId,
    required this.organizationName,
    required this.workspaceName,
    required this.attention,
    required this.priorityItems,
    required this.latestResult,
    required this.updatedAt,
  });

  final String workspaceId;
  final String organizationName;
  final String workspaceName;
  final HomeAttention attention;
  final List<HomePriorityItem> priorityItems;
  final HomeResult? latestResult;
  final DateTime updatedAt;

  factory HomeSummary.fromJson(Map<String, dynamic> json) {
    final latest = json['latest_result'];
    return HomeSummary(
      workspaceId: '${json['workspace_id'] ?? ''}',
      organizationName: '${json['organization_name'] ?? 'GeoVision'}',
      workspaceName: '${json['workspace_name'] ?? ''}',
      attention: HomeAttention.fromJson(
          Map<String, dynamic>.from(json['attention'] as Map? ?? const {})),
      priorityItems: (json['priority_items'] as List? ?? const [])
          .whereType<Map>()
          .map((item) =>
              HomePriorityItem.fromJson(Map<String, dynamic>.from(item)))
          .where((item) => item.appPath != null)
          .toList(),
      latestResult: latest is Map
          ? HomeResult.fromJson(Map<String, dynamic>.from(latest))
          : null,
      updatedAt: DateTime.tryParse('${json['updated_at'] ?? ''}') ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    );
  }
}

int _integer(dynamic value) => (value as num?)?.toInt() ?? 0;
