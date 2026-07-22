import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/integrations/drones/mock_drone_provider.dart';

void main() {
  const provider = MockDroneProvider();

  test('Neo is media-import only and never presented as automated', () async {
    final neo = (await provider.fetchAircraft()).first;
    expect(neo.model, 'DJI Neo');
    expect(neo.sdkSupported, isFalse);
    final result = await provider.readiness(neo);
    expect(result.outcome.name, 'mediaImportOnly');
  });

  test('supported aircraft exposes mission capabilities behind credentials',
      () async {
    final aircraft = (await provider.fetchAircraft())[1];
    expect(aircraft.sdkSupported, isTrue);
    expect(aircraft.capabilities, contains('mission_planning'));
    final result = await provider.readiness(aircraft);
    expect(result.outcome.name, 'credentialsRequired');
  });

  test('Neo media can be staged for the offline upload flow', () async {
    final neo = (await provider.fetchAircraft()).first;
    final result = await provider.stageMedia(neo, ['/tmp/flight-001.jpg']);
    expect(result.outcome.name, 'ready');
  });
}
