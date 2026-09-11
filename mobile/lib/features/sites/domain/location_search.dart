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
