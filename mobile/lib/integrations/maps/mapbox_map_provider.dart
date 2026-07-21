import '../../features/sites/domain/site.dart';
import 'map_provider.dart';

/// PLACEHOLDER real provider. Interface is prepared; wiring the mapbox_gl /
/// flutter_map tile source is gated on GV_MAPBOX_TOKEN. See INTEGRATIONS.md.
class MapboxMapProvider implements MapProvider {
  const MapboxMapProvider(this.accessToken);
  final String accessToken;
  @override
  String get id => 'mapbox';
  @override
  bool get requiresCredentials => true;
  @override
  String? tileUrlTemplate() =>
      'https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/{z}/{x}/{y}?access_token=$accessToken';
  @override
  List<MapLayer> layersForSite(Site site) => const [
        MapLayer(id: 'boundary', name: 'Site boundary', enabledByDefault: true),
        MapLayer(id: 'fields', name: 'Fields', enabledByDefault: true),
        MapLayer(id: 'ndvi', name: 'NDVI overlay', enabledByDefault: false),
      ];
}
