class GvAlert {
  const GvAlert({
    required this.id,
    required this.severity,
    required this.sector,
    required this.title,
    required this.description,
    this.siteId,
    this.location,
    required this.createdAt,
    this.acknowledged = false,
    this.resolved = false,
    this.recommendation,
    this.evidence = const [],
    this.lat,
    this.lng,
  });

  final String id;
  final String severity; // information|low|medium|high|critical
  final String sector;
  final String title;
  final String description;
  final String? siteId;
  final String? location;
  final DateTime createdAt;
  final bool acknowledged;
  final bool resolved;
  final String? recommendation;
  final List<String> evidence;
  final double? lat;
  final double? lng;

  GvAlert copyWith({bool? acknowledged, bool? resolved}) => GvAlert(
        id: id,
        severity: severity,
        sector: sector,
        title: title,
        description: description,
        siteId: siteId,
        location: location,
        createdAt: createdAt,
        acknowledged: acknowledged ?? this.acknowledged,
        resolved: resolved ?? this.resolved,
        recommendation: recommendation,
        evidence: evidence,
        lat: lat,
        lng: lng,
      );

  factory GvAlert.fromJson(Map<String, dynamic> j) => GvAlert(
        id: j['id'].toString(),
        severity: (j['severity'] ?? 'information').toString(),
        sector: (j['sector'] ?? 'agriculture').toString(),
        title: (j['title'] ?? '').toString(),
        description: (j['description'] ?? '').toString(),
        siteId: j['site_id']?.toString(),
        location: j['location'] as String?,
        createdAt: DateTime.tryParse('${j['created_at'] ?? ''}') ??
            DateTime.now().toUtc(),
        acknowledged: j['acknowledged'] as bool? ?? false,
        resolved: j['resolved'] as bool? ?? false,
        recommendation: j['recommendation'] as String?,
        evidence: (j['evidence'] as List?)?.map((e) => e.toString()).toList() ??
            const [],
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'severity': severity,
        'sector': sector,
        'title': title,
        'description': description,
        'site_id': siteId,
        'location': location,
        'created_at': createdAt.toIso8601String(),
        'acknowledged': acknowledged,
        'resolved': resolved,
        'recommendation': recommendation,
        'evidence': evidence,
        'lat': lat,
        'lng': lng,
      };
}
