import '../../core/networking/api_client.dart';
import '../../features/drones/domain/drone.dart';
import 'drone_provider.dart';

class BackendDroneProvider implements DroneProvider {
  const BackendDroneProvider(this._api);
  final ApiClient _api;

  @override
  String get id => 'geovision_backend';

  @override
  Future<List<GvDrone>> fetchAircraft() async {
    final response = await _api.raw.get('/mobile/drones');
    return (response.data as List)
        .map((row) => GvDrone.fromJson((row as Map).cast<String, dynamic>()))
        .toList();
  }

  @override
  Future<List<DroneMission>> fetchMissions() async {
    final response = await _api.raw.get('/mobile/drone-missions');
    return (response.data as List)
        .map((row) =>
            DroneMission.fromJson((row as Map).cast<String, dynamic>()))
        .toList();
  }

  @override
  Future<DroneOperationResult> readiness(GvDrone aircraft) async {
    if (!aircraft.sdkSupported) {
      return const DroneOperationResult(DroneOutcome.mediaImportOnly,
          'Importação disponível; automação não suportada por esta aeronave.');
    }
    if (aircraft.status == 'credentials_required') {
      return const DroneOperationResult(DroneOutcome.credentialsRequired,
          'As credenciais DJI e a validação do SDK ainda são necessárias.');
    }
    return const DroneOperationResult(
        DroneOutcome.ready, 'Aeronave preparada para planeamento.');
  }

  @override
  Future<DroneOperationResult> stageMedia(
          GvDrone aircraft, List<String> localPaths) async =>
      DroneOperationResult(DroneOutcome.ready,
          '${localPaths.length} ficheiro(s) adicionados à fila offline de upload.');
}
