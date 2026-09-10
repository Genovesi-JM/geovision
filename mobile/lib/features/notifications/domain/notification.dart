/// Customer-visible notification persisted by the GeoVision backend.
class GvNotification {
  const GvNotification({
    required this.id,
    required this.organizationId,
    required this.category,
    required this.type,
    required this.title,
    required this.body,
    required this.severity,
    required this.targetType,
    required this.occurrenceCount,
    required this.firstOccurredAt,
    required this.lastOccurredAt,
    required this.createdAt,
    this.workspaceId,
    this.targetId,
    this.readAt,
  });

  final String id;
  final String organizationId;
  final String? workspaceId;
  final String category;
  final String type;
  final String title;
  final String body;
  final String severity;
  final String targetType;
  final String? targetId;
  final int occurrenceCount;
  final DateTime firstOccurredAt;
  final DateTime lastOccurredAt;
  final DateTime? readAt;
  final DateTime createdAt;

  bool get isRead => readAt != null;

  GvNotification copyWith({DateTime? readAt}) => GvNotification(
        id: id,
        organizationId: organizationId,
        workspaceId: workspaceId,
        category: category,
        type: type,
        title: title,
        body: body,
        severity: severity,
        targetType: targetType,
        targetId: targetId,
        occurrenceCount: occurrenceCount,
        firstOccurredAt: firstOccurredAt,
        lastOccurredAt: lastOccurredAt,
        readAt: readAt ?? this.readAt,
        createdAt: createdAt,
      );

  factory GvNotification.fromJson(Map<String, dynamic> json) => GvNotification(
        id: '${json['id']}',
        organizationId: '${json['organization_id']}',
        workspaceId: json['workspace_id']?.toString(),
        category: '${json['category'] ?? 'SYSTEM'}'.toUpperCase(),
        type: '${json['notification_type'] ?? 'system.notice'}',
        title: '${json['title'] ?? ''}',
        body: '${json['body'] ?? ''}',
        severity: '${json['severity'] ?? 'INFO'}'.toUpperCase(),
        targetType: '${json['target_type'] ?? 'NONE'}'.toUpperCase(),
        targetId: json['target_id']?.toString(),
        occurrenceCount: (json['occurrence_count'] as num?)?.toInt() ?? 1,
        firstOccurredAt: _date(json['first_occurred_at']),
        lastOccurredAt: _date(json['last_occurred_at']),
        readAt: _optionalDate(json['read_at']),
        createdAt: _date(json['created_at']),
      );

  static DateTime _date(Object? value) =>
      DateTime.tryParse('$value') ?? DateTime.fromMillisecondsSinceEpoch(0);

  static DateTime? _optionalDate(Object? value) =>
      value == null ? null : DateTime.tryParse('$value');
}

class NotificationPage {
  const NotificationPage({
    required this.items,
    required this.total,
    required this.unread,
  });

  final List<GvNotification> items;
  final int total;
  final int unread;

  NotificationPage copyWith({
    List<GvNotification>? items,
    int? total,
    int? unread,
  }) =>
      NotificationPage(
        items: items ?? this.items,
        total: total ?? this.total,
        unread: unread ?? this.unread,
      );

  factory NotificationPage.fromJson(Map<String, dynamic> json) {
    final rows = json['items'] as List? ?? const [];
    return NotificationPage(
      items: rows
          .whereType<Map>()
          .map((row) => GvNotification.fromJson(Map<String, dynamic>.from(row)))
          .toList(growable: false),
      total: (json['total'] as num?)?.toInt() ?? rows.length,
      unread: (json['unread'] as num?)?.toInt() ?? 0,
    );
  }
}

class NotificationTarget {
  const NotificationTarget({
    required this.notificationId,
    required this.type,
    required this.id,
    required this.appPath,
    this.workspaceId,
  });

  final String notificationId;
  final String type;
  final String id;
  final String? workspaceId;
  final String appPath;

  factory NotificationTarget.fromJson(Map<String, dynamic> json) =>
      NotificationTarget(
        notificationId: '${json['notification_id']}',
        type: '${json['target_type']}'.toUpperCase(),
        id: '${json['target_id']}',
        workspaceId: json['workspace_id']?.toString(),
        appPath: '${json['app_path']}',
      );

  /// Defense in depth: the backend authorizes and resolves the target, then
  /// the client accepts only the finite set of app-owned route shapes.
  bool get hasSafeAppPath => isSafeNotificationAppPath(appPath);
}

bool isSafeNotificationAppPath(String path) {
  final uri = Uri.tryParse(path);
  if (uri == null ||
      uri.hasScheme ||
      uri.host.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      !path.startsWith('/') ||
      path.startsWith('//')) {
    return false;
  }
  if (path == '/portal') return true;
  return RegExp(
    r'^/(?:assets|reports|actions|orders|services)/[A-Za-z0-9_-]+$',
  ).hasMatch(path);
}

/// Verifies that a server-resolved path matches both the target type and id.
/// This prevents a malformed provider payload from crossing feature boundaries.
bool isSafeNotificationTarget(NotificationTarget target) {
  if (!target.hasSafeAppPath) return false;
  final expected = switch (target.type) {
    'ASSET' => '/assets/${target.id}',
    'REPORT' => '/reports/${target.id}',
    'ACTION' => '/actions/${target.id}',
    'ORDER' || 'SHIPMENT' => '/orders/${target.id}',
    'SERVICE' => '/services/${target.id}',
    'INVITATION' => '/portal',
    _ => null,
  };
  return expected != null && target.appPath == expected;
}

class NotificationContextDetails {
  const NotificationContextDetails({
    required this.type,
    required this.id,
    required this.title,
    required this.status,
    this.description,
    this.facts = const {},
  });

  final String type;
  final String id;
  final String title;
  final String status;
  final String? description;
  final Map<String, String> facts;
}

const notificationCategories = <String>[
  'INVITATION',
  'REPORT',
  'ACTION',
  'DEVICE',
  'SERVICE',
  'ORDER',
  'SHIPMENT',
  'SYSTEM',
];

class NotificationPreference {
  const NotificationPreference({
    required this.category,
    required this.inAppEnabled,
    required this.pushEnabled,
    required this.emailEnabled,
    required this.smsEnabled,
    required this.minimumSeverity,
    this.organizationId,
    this.quietHoursStart,
    this.quietHoursEnd,
    this.timezone = 'UTC',
  });

  final String? organizationId;
  final String category;
  final bool inAppEnabled;
  final bool pushEnabled;
  final bool emailEnabled;
  final bool smsEnabled;
  final String minimumSeverity;
  final String? quietHoursStart;
  final String? quietHoursEnd;
  final String timezone;

  factory NotificationPreference.defaults(String category) =>
      NotificationPreference(
        category: category,
        inAppEnabled: true,
        pushEnabled: true,
        emailEnabled: true,
        smsEnabled: false,
        minimumSeverity: 'INFO',
      );

  factory NotificationPreference.fromJson(Map<String, dynamic> json) =>
      NotificationPreference(
        organizationId: json['organization_id']?.toString(),
        category: '${json['category']}'.toUpperCase(),
        inAppEnabled: json['in_app_enabled'] != false,
        pushEnabled: json['push_enabled'] != false,
        emailEnabled: json['email_enabled'] != false,
        smsEnabled: json['sms_enabled'] == true,
        minimumSeverity: '${json['minimum_severity'] ?? 'INFO'}'.toUpperCase(),
        quietHoursStart: json['quiet_hours_start']?.toString(),
        quietHoursEnd: json['quiet_hours_end']?.toString(),
        timezone: '${json['timezone'] ?? 'UTC'}',
      );

  NotificationPreference copyWith({
    bool? inAppEnabled,
    bool? pushEnabled,
    bool? emailEnabled,
    bool? smsEnabled,
    String? minimumSeverity,
  }) =>
      NotificationPreference(
        organizationId: organizationId,
        category: category,
        inAppEnabled: inAppEnabled ?? this.inAppEnabled,
        pushEnabled: pushEnabled ?? this.pushEnabled,
        emailEnabled: emailEnabled ?? this.emailEnabled,
        smsEnabled: smsEnabled ?? this.smsEnabled,
        minimumSeverity: minimumSeverity ?? this.minimumSeverity,
        quietHoursStart: quietHoursStart,
        quietHoursEnd: quietHoursEnd,
        timezone: timezone,
      );

  Map<String, dynamic> toJson() => {
        'organization_id': organizationId,
        'category': category,
        'in_app_enabled': inAppEnabled,
        'push_enabled': pushEnabled,
        'email_enabled': emailEnabled,
        'sms_enabled': smsEnabled,
        'minimum_severity': minimumSeverity,
        'quiet_hours_start': quietHoursStart,
        'quiet_hours_end': quietHoursEnd,
        'timezone': timezone,
      };
}
