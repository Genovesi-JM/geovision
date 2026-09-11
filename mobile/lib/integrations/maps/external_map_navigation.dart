import 'package:url_launcher/url_launcher.dart';

/// Builds allowlisted navigation URLs from validated coordinates only.
///
/// These universal links do not use a Maps API key and do not grant GeoVision
/// access to route, traffic, fleet, or location-history data.
class ExternalMapNavigation {
  const ExternalMapNavigation();

  Uri googleDirections({
    required double latitude,
    required double longitude,
  }) {
    _validate(latitude, longitude);
    return Uri.https('www.google.com', '/maps/dir/', {
      'api': '1',
      'destination': '$latitude,$longitude',
      'travelmode': 'driving',
    });
  }

  Uri appleDirections({
    required double latitude,
    required double longitude,
    String? label,
  }) {
    _validate(latitude, longitude);
    final safeLabel = label?.trim();
    return Uri.https('maps.apple.com', '/', {
      'daddr': '$latitude,$longitude',
      'dirflg': 'd',
      if (safeLabel != null && safeLabel.isNotEmpty) 'q': safeLabel,
    });
  }

  Future<bool> open(Uri uri) {
    if (!_isAllowlisted(uri)) return Future.value(false);
    return launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  bool _isAllowlisted(Uri uri) =>
      uri.scheme == 'https' &&
      const {'www.google.com', 'maps.apple.com'}.contains(uri.host);

  void _validate(double latitude, double longitude) {
    if (!latitude.isFinite ||
        !longitude.isFinite ||
        latitude < -90 ||
        latitude > 90 ||
        longitude < -180 ||
        longitude > 180) {
      throw ArgumentError('Invalid map coordinates.');
    }
  }
}
