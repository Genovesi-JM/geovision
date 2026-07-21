import '../../features/sites/domain/site.dart';
import 'map_provider.dart';

/// Credential-free provider. The map screen renders site boundaries, field
/// polygons and markers on a locally-painted canvas — no network tiles.
class DemoMapProvider implements MapProvider {
  const DemoMapProvider();
  @override
  String get id => 'demo';
  @override
  bool get requiresCredentials => false;
  @override
  String? tileUrlTemplate() => null;
  @override
  List<MapLayer> layersForSite(Site site) => const [
        MapLayer(id: 'boundary', name: 'Site boundary', enabledByDefault: true),
        MapLayer(id: 'fields', name: 'Fields', enabledByDefault: true),
        MapLayer(id: 'ndvi', name: 'NDVI overlay', enabledByDefault: true),
        MapLayer(id: 'alerts', name: 'Alerts', enabledByDefault: true),
        MapLayer(id: 'devices', name: 'Devices', enabledByDefault: false),
      ];
}
