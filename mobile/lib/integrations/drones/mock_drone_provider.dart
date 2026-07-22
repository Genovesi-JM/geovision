import '../../features/drones/domain/drone.dart';
import 'drone_provider.dart';

class MockDroneProvider implements DroneProvider {
  const MockDroneProvider();

  @override
  String get id => 'mock_dji';

  @override
  Future<List<GvDrone>> fetchAircraft() async => const [
        GvDrone(
          id: 'neo-01',
          name: 'GeoVision DJI Neo',
          model: 'DJI Neo',
          provider: 'manual_import',
          connectionMode: 'media_import',
          sdkSupported: false,
          status: 'registered',
          capabilities: ['media_import', 'operation_history'],
        ),
        GvDrone(
          id: 'm3e-ready',
          name: 'Aeronave profissional (por configurar)',
          model: 'DJI Mavic 3 Enterprise',
          provider: 'dji_mobile_sdk',
          connectionMode: 'sdk_handoff',
          sdkSupported: true,
          status: 'credentials_required',
          capabilities: ['mission_planning', 'telemetry', 'media_sync'],
        ),
      ];

  @override
  Future<List<DroneMission>> fetchMissions() async => const [
        DroneMission(
          id: 'mission-demo-01',
          siteId: 'site-fazenda-kizua',
          aircraftId: 'm3e-ready',
          name: 'Mapeamento do Bloco A',
          type: 'mapping_grid',
          status: 'draft',
          altitudeM: 80,
          frontOverlap: 80,
          sideOverlap: 70,
        ),
      ];

  @override
  Future<DroneOperationResult> readiness(GvDrone aircraft) async {
    if (!aircraft.sdkSupported) {
      return const DroneOperationResult(
        DroneOutcome.mediaImportOnly,
        'O DJI Neo pode importar fotografias e vídeos, mas não aceita missões programadas pelo SDK.',
      );
    }
    return const DroneOperationResult(
      DroneOutcome.credentialsRequired,
      'Registe a aplicação no DJI Developer e valide a aeronave antes de executar missões.',
      retryable: true,
    );
  }

  @override
  Future<DroneOperationResult> stageMedia(
      GvDrone aircraft, List<String> localPaths) async {
    if (localPaths.isEmpty) {
      return const DroneOperationResult(
          DroneOutcome.permissionRequired, 'Nenhum ficheiro foi selecionado.');
    }
    return DroneOperationResult(DroneOutcome.ready,
        '${localPaths.length} ficheiro(s) preparados para associar a um local e enviar.');
  }
}
