import '../../features/sites/domain/site.dart';

/// Provider-neutral raster map contract.
///
/// Credentials are resolved at the application composition boundary. Screens
/// receive only this safe rendering contract and never read secrets directly.
abstract interface class MapProvider {
  String get id;
  String get displayName;
  bool get requiresCredentials;
  String get attribution;
  double get maxZoom;

  /// Returns an XYZ raster tile URL template, or null for a locally-drawn
  /// demo canvas.
  String? tileUrlTemplate();

  /// Optional named layers the customer can toggle (NDVI, thermal, etc).
  List<MapLayer> layersForSite(Site site);
}

class MapLayer {
  const MapLayer(
      {required this.id, required this.name, required this.enabledByDefault});
  final String id;
  final String name;
  final bool enabledByDefault;
}
