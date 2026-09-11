import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/integrations/maps/demo_map_provider.dart';
import 'package:geovision/integrations/maps/mapbox_map_provider.dart';
import 'package:geovision/integrations/maps/open_street_map_provider.dart';

void main() {
  test('demo provider remains credential and network independent', () {
    const provider = DemoMapProvider();

    expect(provider.id, 'demo');
    expect(provider.requiresCredentials, isFalse);
    expect(provider.tileUrlTemplate(), isNull);
  });

  test('OpenStreetMap provider declares tiles and attribution', () {
    const provider = OpenStreetMapProvider();

    expect(provider.requiresCredentials, isFalse);
    expect(provider.tileUrlTemplate(), contains('openstreetmap.org'));
    expect(provider.attribution, contains('OpenStreetMap'));
  });

  test('Mapbox provider encodes its public token in the tile URL', () {
    const provider = MapboxMapProvider('token with spaces&scope=bad');
    final url = provider.tileUrlTemplate()!;

    expect(provider.requiresCredentials, isTrue);
    expect(url, contains('satellite-streets-v12'));
    expect(url, contains('token+with+spaces%26scope%3Dbad'));
    expect(url, isNot(contains('token with spaces')));
  });
}
