class CustomerAsset {
  const CustomerAsset({
    required this.id,
    required this.name,
    required this.sector,
    required this.assetType,
    required this.status,
    required this.locationLabel,
    required this.description,
    required this.metadata,
    required this.childrenCount,
    this.parentAssetId,
    this.latitude,
    this.longitude,
    this.updatedAt,
  });

  final String id;
  final String name;
  final String sector;
  final String assetType;
  final String status;
  final String locationLabel;
  final String description;
  final Map<String, dynamic> metadata;
  final int childrenCount;
  final String? parentAssetId;
  final double? latitude;
  final double? longitude;
  final DateTime? updatedAt;

  bool get hasLocation => latitude != null && longitude != null;

  factory CustomerAsset.fromJson(Map<String, dynamic> json) {
    final center = Map<String, dynamic>.from(
      json['center'] as Map? ?? const <String, dynamic>{},
    );
    final geometry = Map<String, dynamic>.from(
      json['geometry'] as Map? ?? const <String, dynamic>{},
    );
    final coordinates =
        geometry['type'] == 'Point' ? geometry['coordinates'] as List? : null;
    final bbox = json['bbox'] as List?;
    final centerLat = _number(center['lat']) ??
        (coordinates != null && coordinates.length >= 2
            ? _number(coordinates[1])
            : null) ??
        (bbox != null && bbox.length >= 4
            ? ((_number(bbox[1]) ?? 0) + (_number(bbox[3]) ?? 0)) / 2
            : null);
    final centerLng = _number(center['lng']) ??
        (coordinates != null && coordinates.length >= 2
            ? _number(coordinates[0])
            : null) ??
        (bbox != null && bbox.length >= 4
            ? ((_number(bbox[0]) ?? 0) + (_number(bbox[2]) ?? 0)) / 2
            : null);

    return CustomerAsset(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? 'Asset'}',
      sector: '${json['sector'] ?? 'OTHER'}'.toUpperCase(),
      assetType: '${json['asset_type'] ?? 'ASSET'}'.toUpperCase(),
      status: '${json['status'] ?? 'active'}'.toLowerCase(),
      locationLabel: '${json['location_label'] ?? ''}',
      description: '${json['description'] ?? ''}',
      metadata: Map<String, dynamic>.from(
        json['metadata'] as Map? ?? const <String, dynamic>{},
      ),
      childrenCount: (json['children_count'] as num?)?.toInt() ?? 0,
      parentAssetId: json['parent_asset_id']?.toString(),
      latitude: centerLat,
      longitude: centerLng,
      updatedAt: DateTime.tryParse('${json['updated_at'] ?? ''}'),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'sector': sector,
        'asset_type': assetType,
        'status': status,
        'location_label': locationLabel,
        'description': description,
        'metadata': metadata,
        'children_count': childrenCount,
        'parent_asset_id': parentAssetId,
        if (hasLocation) 'center': {'lat': latitude, 'lng': longitude},
        'updated_at': updatedAt?.toIso8601String(),
      };
}

double? _number(dynamic value) =>
    value is num ? value.toDouble() : double.tryParse(value?.toString() ?? '');
