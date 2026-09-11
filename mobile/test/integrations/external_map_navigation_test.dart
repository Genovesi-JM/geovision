import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/integrations/maps/external_map_navigation.dart';

void main() {
  const navigation = ExternalMapNavigation();

  test('builds an allowlisted Google Maps driving URL', () {
    final uri = navigation.googleDirections(
      latitude: -8.838333,
      longitude: 13.234444,
    );

    expect(uri.scheme, 'https');
    expect(uri.host, 'www.google.com');
    expect(uri.path, '/maps/dir/');
    expect(uri.queryParameters['api'], '1');
    expect(uri.queryParameters['destination'], '-8.838333,13.234444');
    expect(uri.queryParameters['travelmode'], 'driving');
  });

  test('encodes an asset label without changing the Apple Maps host', () {
    final uri = navigation.appleDirections(
      latitude: 40.4168,
      longitude: -3.7038,
      label: 'Madrid & outside=https://attacker.test',
    );

    expect(uri.scheme, 'https');
    expect(uri.host, 'maps.apple.com');
    expect(uri.queryParameters['daddr'], '40.4168,-3.7038');
    expect(uri.queryParameters['q'], 'Madrid & outside=https://attacker.test');
    expect(uri.queryParameters.containsKey('outside'), isFalse);
  });

  test('rejects coordinates outside Earth bounds', () {
    expect(
      () => navigation.googleDirections(latitude: 91, longitude: 13),
      throwsArgumentError,
    );
    expect(
      () => navigation.appleDirections(latitude: 40, longitude: -181),
      throwsArgumentError,
    );
    expect(
      () => navigation.googleDirections(
        latitude: double.nan,
        longitude: 13,
      ),
      throwsArgumentError,
    );
  });
}
