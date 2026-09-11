import '../../features/sites/domain/site.dart';
import 'map_provider.dart';

/// Credential-free raster tiles for development, pilots, and manual location
/// selection. Production volume must follow the OpenStreetMap tile policy or
/// use an approved commercial tile host.
class OpenStreetMapProvider implements MapProvider {
  const OpenStreetMapProvider();

  @override
  String get id => 'openstreetmap';

  @override
  String get displayName => 'OpenStreetMap';

  @override
  bool get requiresCredentials => false;

  @override
  String get attribution => '© OpenStreetMap contributors';

  @override
  double get maxZoom => 19;

  @override
  String tileUrlTemplate() => 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

  @override
  List<MapLayer> layersForSite(Site site) => const [
        MapLayer(id: 'boundary', name: 'Site boundary', enabledByDefault: true),
        MapLayer(id: 'fields', name: 'Fields', enabledByDefault: true),
        MapLayer(id: 'alerts', name: 'Alerts', enabledByDefault: true),
        MapLayer(id: 'devices', name: 'Devices', enabledByDefault: false),
      ];
}
