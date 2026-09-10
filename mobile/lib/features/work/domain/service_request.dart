enum ServiceType {
  droneOperation,
  inspection,
  deviceInstall,
  maintenance,
  problemReport
}

extension ServiceTypeX on ServiceType {
  String get label {
    switch (this) {
      case ServiceType.droneOperation:
        return 'Drone operation';
      case ServiceType.inspection:
        return 'Inspection';
      case ServiceType.deviceInstall:
        return 'Device installation';
      case ServiceType.maintenance:
        return 'Maintenance';
      case ServiceType.problemReport:
        return 'Report a problem';
    }
  }
}

class ServiceRequest {
  const ServiceRequest({
    required this.id,
    required this.type,
    required this.siteId,
    required this.siteName,
    required this.urgency,
    required this.description,
    required this.status,
    required this.createdAt,
    this.progressPercent = 0,
    this.pendingSync = false,
    this.attachments = const [],
    this.assignedTeam,
    this.resultTitle,
    this.resultSummary,
    this.resultReportId,
    this.resultAssetId,
    this.resultPublishedAt,
  });

  final String id;
  final String type; // matches ServiceType.name
  final String siteId;
  final String siteName;
  final String urgency; // low|normal|high|critical
  final String description;
  final String status; // submitted|scheduled|in_field|processing|completed
  final DateTime createdAt;
  final int progressPercent;
  final bool pendingSync;
  final List<String> attachments;
  final String? assignedTeam;
  final String? resultTitle;
  final String? resultSummary;
  final String? resultReportId;
  final String? resultAssetId;
  final DateTime? resultPublishedAt;

  factory ServiceRequest.fromJson(Map<String, dynamic> j) {
    final result = Map<String, dynamic>.from(j['result'] as Map? ?? const {});
    return ServiceRequest(
      id: j['id'].toString(),
      type: (j['type'] ?? 'inspection').toString(),
      siteId: (j['site_id'] ?? '').toString(),
      siteName: (j['site_name'] ?? '').toString(),
      urgency: (j['urgency'] ?? 'normal').toString(),
      description: (j['description'] ?? '').toString(),
      status: (j['status'] ?? 'submitted').toString(),
      createdAt: DateTime.tryParse('${j['created_at'] ?? ''}') ??
          DateTime.now().toUtc(),
      progressPercent: (j['progress_percent'] as num?)?.toInt() ?? 0,
      pendingSync: j['pending_sync'] as bool? ?? false,
      attachments:
          (j['attachments'] as List?)?.map((e) => e.toString()).toList() ??
              const [],
      assignedTeam: j['assigned_team'] as String?,
      resultTitle: result['title']?.toString(),
      resultSummary: result['summary']?.toString(),
      resultReportId: result['report_id']?.toString(),
      resultAssetId: result['asset_id']?.toString(),
      resultPublishedAt: DateTime.tryParse('${result['published_at'] ?? ''}'),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type,
        'site_id': siteId,
        'site_name': siteName,
        'urgency': urgency,
        'description': description,
        'status': status,
        'created_at': createdAt.toIso8601String(),
        'progress_percent': progressPercent,
        'pending_sync': pendingSync,
        'attachments': attachments,
        'assigned_team': assignedTeam,
        if (resultTitle != null || resultReportId != null)
          'result': {
            'title': resultTitle,
            'summary': resultSummary,
            'report_id': resultReportId,
            'asset_id': resultAssetId,
            'published_at': resultPublishedAt?.toIso8601String(),
          },
      };
}
