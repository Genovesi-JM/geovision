class LocationSuggestion {
  const LocationSuggestion({
    required this.providerReference,
    required this.primaryText,
    required this.secondaryText,
  });

  final String providerReference;
  final String primaryText;
  final String secondaryText;

  factory LocationSuggestion.fromJson(Map<String, dynamic> json) =>
      LocationSuggestion(
        providerReference: json['provider_reference'] as String,
        primaryText: json['primary_text'] as String,
        secondaryText: json['secondary_text'] as String? ?? '',
      );
}

class ResolvedLocation {
  const ResolvedLocation({
    required this.providerReference,
    required this.displayName,
    required this.formattedAddress,
    required this.latitude,
    required this.longitude,
  });

  final String providerReference;
  final String displayName;
  final String formattedAddress;
  final double latitude;
  final double longitude;

  factory ResolvedLocation.fromJson(Map<String, dynamic> json) {
    final coordinate =
        Map<String, dynamic>.from(json['coordinate'] as Map<dynamic, dynamic>);
    return ResolvedLocation(
      providerReference: json['provider_reference'] as String,
      displayName: json['display_name'] as String,
      formattedAddress: json['formatted_address'] as String,
      latitude: (coordinate['latitude'] as num).toDouble(),
      longitude: (coordinate['longitude'] as num).toDouble(),
    );
  }
}

class RouteEstimate {
  const RouteEstimate({
    required this.provider,
    required this.simulated,
    required this.distanceMeters,
    required this.durationSeconds,
    required this.trafficAware,
    this.encodedPolyline,
  });

  final String provider;
  final bool simulated;
  final int distanceMeters;
  final int durationSeconds;
  final bool trafficAware;
  final String? encodedPolyline;

  factory RouteEstimate.fromJson(Map<String, dynamic> json) => RouteEstimate(
        provider: json['provider'] as String,
        simulated: json['simulated'] as bool? ?? false,
        distanceMeters: (json['distance_meters'] as num).round(),
        durationSeconds: (json['duration_seconds'] as num).round(),
        trafficAware: json['traffic_aware'] as bool? ?? false,
        encodedPolyline: json['encoded_polyline'] as String?,
      );
}

class ReverseGeocodedAddress {
  const ReverseGeocodedAddress({
    required this.provider,
    required this.simulated,
    required this.providerReference,
    required this.formattedAddress,
    required this.latitude,
    required this.longitude,
    this.granularity,
  });

  final String provider;
  final bool simulated;
  final String providerReference;
  final String formattedAddress;
  final double latitude;
  final double longitude;
  final String? granularity;

  factory ReverseGeocodedAddress.fromJson(Map<String, dynamic> json) {
    final coordinate =
        Map<String, dynamic>.from(json['coordinate'] as Map<dynamic, dynamic>);
    return ReverseGeocodedAddress(
      provider: json['provider'] as String,
      simulated: json['simulated'] as bool? ?? false,
      providerReference: json['provider_reference'] as String,
      formattedAddress: json['formatted_address'] as String,
      latitude: (coordinate['latitude'] as num).toDouble(),
      longitude: (coordinate['longitude'] as num).toDouble(),
      granularity: json['granularity'] as String?,
    );
  }
}
