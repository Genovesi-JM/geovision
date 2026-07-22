import '../../features/drones/domain/drone.dart';

abstract interface class DroneProvider {
  String get id;
  Future<List<GvDrone>> fetchAircraft();
  Future<List<DroneMission>> fetchMissions();
  Future<DroneOperationResult> readiness(GvDrone aircraft);
  Future<DroneOperationResult> stageMedia(
      GvDrone aircraft, List<String> localPaths);
}
