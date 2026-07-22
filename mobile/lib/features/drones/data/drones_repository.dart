import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../integrations/drones/drone_provider.dart';
import '../domain/drone.dart';

class DronesRepository {
  const DronesRepository(this._provider);
  final DroneProvider _provider;

  Future<List<GvDrone>> aircraft() => _provider.fetchAircraft();
  Future<List<DroneMission>> missions() => _provider.fetchMissions();
  Future<DroneOperationResult> readiness(GvDrone aircraft) =>
      _provider.readiness(aircraft);
  Future<DroneOperationResult> stageMedia(
          GvDrone aircraft, List<String> localPaths) =>
      _provider.stageMedia(aircraft, localPaths);
}

final dronesRepositoryProvider = Provider<DronesRepository>(
    (ref) => DronesRepository(ref.watch(droneProviderProvider)));
final aircraftProvider = FutureProvider<List<GvDrone>>(
    (ref) => ref.watch(dronesRepositoryProvider).aircraft());
final droneMissionsProvider = FutureProvider<List<DroneMission>>(
    (ref) => ref.watch(dronesRepositoryProvider).missions());
