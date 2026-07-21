import 'sector.dart';

enum SiteStatus { active, attention, offline }

SiteStatus siteStatusFromString(String v) {
  switch (v) {
    case 'attention':
      return SiteStatus.attention;
    case 'offline':
      return SiteStatus.offline;
    default:
      return SiteStatus.active;
  }
}

/// A measured KPI value tied to a definition id.
class KpiValue {
  const KpiValue({
    required this.definitionId,
    required this.label,
    required this.value,
    this.unit,
    this.status = 'ok',
    this.trend = 'stable',
    this.spark = const [],
    this.description,
    required this.updatedAt,
  });

  final String definitionId;
  final String label;
  final num value;
  final String? unit;
  final String status; // ok | warning | critical
  final String trend; // up | down | stable
  final List<double> spark;
  final String? description;
  final DateTime updatedAt;

  factory KpiValue.fromJson(Map<String, dynamic> j) => KpiValue(
        definitionId: (j['id'] ?? j['definitionId'] ?? '').toString(),
        label: (j['label'] ?? '').toString(),
        value: (j['value'] is num)
            ? j['value'] as num
            : num.tryParse('${j['value']}') ?? 0,
        unit: j['unit'] as String?,
        status: (j['status'] ?? 'ok').toString(),
        trend: (j['trend'] ?? 'stable').toString(),
        spark:
            (j['spark'] as List?)?.map((e) => (e as num).toDouble()).toList() ??
                const [],
        description: j['description'] as String?,
        updatedAt:
            DateTime.tryParse('${j['updated_at'] ?? j['updatedAt'] ?? ''}') ??
                DateTime.now().toUtc(),
      );

  Map<String, dynamic> toJson() => {
        'id': definitionId,
        'label': label,
        'value': value,
        'unit': unit,
        'status': status,
        'trend': trend,
        'spark': spark,
        'description': description,
        'updated_at': updatedAt.toIso8601String(),
      };
}

/// A field / area / parcel inside a site.
class SiteArea {
  const SiteArea({
    required this.id,
    required this.name,
    required this.hectares,
    required this.crop,
    this.kpis = const [],
  });
  final String id;
  final String name;
  final double hectares;
  final String crop;
  final List<KpiValue> kpis;

  factory SiteArea.fromJson(Map<String, dynamic> j) => SiteArea(
        id: j['id'].toString(),
        name: j['name'].toString(),
        hectares: (j['hectares'] as num).toDouble(),
        crop: (j['crop'] ?? '').toString(),
        kpis: (j['kpis'] as List?)
                ?.map((e) =>
                    KpiValue.fromJson((e as Map).cast<String, dynamic>()))
                .toList() ??
            const [],
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'hectares': hectares,
        'crop': crop,
        'kpis': kpis.map((e) => e.toJson()).toList(),
      };
}

class GeoPoint {
  const GeoPoint(this.lat, this.lng);
  final double lat;
  final double lng;
  factory GeoPoint.fromJson(Map<String, dynamic> j) =>
      GeoPoint((j['lat'] as num).toDouble(), (j['lng'] as num).toDouble());
  Map<String, dynamic> toJson() => {'lat': lat, 'lng': lng};
}

class Site {
  const Site({
    required this.id,
    required this.name,
    required this.sector,
    required this.status,
    required this.location,
    required this.center,
    this.boundary = const [],
    this.areas = const [],
    this.kpis = const [],
    this.totalHectares = 0,
    this.openAlerts = 0,
  });

  final String id;
  final String name;
  final Sector sector;
  final SiteStatus status;
  final String location;
  final GeoPoint center;
  final List<GeoPoint> boundary;
  final List<SiteArea> areas;
  final List<KpiValue> kpis;
  final double totalHectares;
  final int openAlerts;

  factory Site.fromJson(Map<String, dynamic> j) => Site(
        id: j['id'].toString(),
        name: j['name'].toString(),
        sector: sectorFromString((j['sector'] ?? 'agriculture').toString()),
        status: siteStatusFromString((j['status'] ?? 'active').toString()),
        location: (j['location'] ?? '').toString(),
        center: GeoPoint.fromJson((j['center'] as Map).cast<String, dynamic>()),
        boundary: (j['boundary'] as List?)
                ?.map((e) =>
                    GeoPoint.fromJson((e as Map).cast<String, dynamic>()))
                .toList() ??
            const [],
        areas: (j['areas'] as List?)
                ?.map((e) =>
                    SiteArea.fromJson((e as Map).cast<String, dynamic>()))
                .toList() ??
            const [],
        kpis: (j['kpis'] as List?)
                ?.map((e) =>
                    KpiValue.fromJson((e as Map).cast<String, dynamic>()))
                .toList() ??
            const [],
        totalHectares: (j['total_hectares'] as num?)?.toDouble() ?? 0,
        openAlerts: (j['open_alerts'] as num?)?.toInt() ?? 0,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'sector': sector.id,
        'status': status.name,
        'location': location,
        'center': center.toJson(),
        'boundary': boundary.map((e) => e.toJson()).toList(),
        'areas': areas.map((e) => e.toJson()).toList(),
        'kpis': kpis.map((e) => e.toJson()).toList(),
        'total_hectares': totalHectares,
        'open_alerts': openAlerts,
      };
}
