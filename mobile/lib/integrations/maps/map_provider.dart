import '../../features/sites/domain/site.dart';

/// Abstract map-tile contract. Concrete providers (demo / Mapbox / ArcGIS)
/// implement this so the map UI is provider-agnostic and always runnable
/// without credentials.
abstract interface class MapProvider {
  String get id;
  bool get requiresCredentials;

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
