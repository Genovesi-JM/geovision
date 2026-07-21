import '../../features/devices/domain/device.dart';

/// Abstract IoT contract. Permanent monitoring lives on the backend; the app
/// consumes mobile-optimised device snapshots and (future) BLE provisioning.
/// Concrete providers: mock, MQTT bridge, vendor SDKs.
abstract interface class IotProvider {
  String get id;
  bool get requiresCredentials;
  Future<List<GvDevice>> fetchDevices();
  Stream<DeviceReading> subscribeReadings(String deviceId);
}

class DeviceReading {
  const DeviceReading(
      {required this.deviceId, required this.label, required this.at});
  final String deviceId;
  final String label;
  final DateTime at;
}
