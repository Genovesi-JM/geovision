class GvReport {
  const GvReport({
    required this.id,
    required this.title,
    required this.siteName,
    required this.type,
    required this.createdAt,
    required this.sizeBytes,
    this.signedUrl,
    this.signedUrlExpiresAt,
  });

  final String id;
  final String title;
  final String siteName;
  final String type; // ndvi|inspection|thermal|topography|summary
  final DateTime createdAt;
  final int sizeBytes;
  final String? signedUrl;
  final DateTime? signedUrlExpiresAt;

  bool get urlValid =>
      signedUrl != null &&
      (signedUrlExpiresAt == null ||
          signedUrlExpiresAt!.isAfter(DateTime.now()));

  factory GvReport.fromJson(Map<String, dynamic> j) => GvReport(
        id: j['id'].toString(),
        title: (j['title'] ?? '').toString(),
        siteName: (j['site_name'] ?? '').toString(),
        type: (j['type'] ?? 'summary').toString(),
        createdAt: DateTime.tryParse('${j['created_at'] ?? ''}') ??
            DateTime.now().toUtc(),
        sizeBytes: (j['size_bytes'] as num?)?.toInt() ?? 0,
        signedUrl: j['signed_url'] as String?,
        signedUrlExpiresAt:
            DateTime.tryParse('${j['signed_url_expires_at'] ?? ''}'),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'site_name': siteName,
        'type': type,
        'created_at': createdAt.toIso8601String(),
        'size_bytes': sizeBytes,
      };
}
