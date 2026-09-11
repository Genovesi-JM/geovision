import '../../features/sites/domain/site.dart';
import 'map_provider.dart';

/// Mapbox raster tiles behind the provider-neutral flutter_map surface.
/// Activation remains gated on a restricted public token and provider review.
class MapboxMapProvider implements MapProvider {
  const MapboxMapProvider(this.accessToken);
  final String accessToken;
  @override
  String get id => 'mapbox';
  @override
  String get displayName => 'Mapbox Satellite';
  @override
  bool get requiresCredentials => true;
  @override
  String get attribution => '© Mapbox © OpenStreetMap';
  @override
  double get maxZoom => 22;
  @override
  String? tileUrlTemplate() =>
      'https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}?access_token=${Uri.encodeQueryComponent(accessToken)}';
  @override
  List<MapLayer> layersForSite(Site site) => const [
        MapLayer(id: 'boundary', name: 'Site boundary', enabledByDefault: true),
        MapLayer(id: 'fields', name: 'Fields', enabledByDefault: true),
        MapLayer(id: 'ndvi', name: 'NDVI overlay', enabledByDefault: false),
      ];
}
