import '../../features/devices/domain/device.dart';

/// Abstract IoT contract. Permanent monitoring lives on the backend; the app
/// consumes mobile-optimised device snapshots and (future) BLE provisioning.
/// Concrete providers: mock, MQTT bridge, vendor SDKs.
abstract interface class IotProvider {
  String get id;
  bool get requiresCredentials;
  Future<List<GvDevice>> fetchDevices();
  Stream<DeviceReading> subscribeReadings(String deviceId);
  Set<IotTransport> get supportedTransports;
  Future<IotOperationResult> diagnose(String deviceId);
  Future<IotOperationResult> provision(DeviceProvisioningRequest request);
  Future<IotOperationResult> sendCommand(DeviceCommand command);
}

enum IotTransport { api, mqtt, webhook, bluetooth, lorawan, modbusGateway }

enum IotOutcome {
  success,
  pending,
  offline,
  permissionRequired,
  credentialsRequired,
  unsupported,
  rejected,
  timeout,
  error,
}

class IotOperationResult {
  const IotOperationResult(this.outcome,
      {this.message, this.retryable = false, this.data = const {}});
  final IotOutcome outcome;
  final String? message;
  final bool retryable;
  final Map<String, Object?> data;
  bool get succeeded => outcome == IotOutcome.success;
}

class DeviceProvisioningRequest {
  const DeviceProvisioningRequest({
    required this.deviceId,
    required this.transport,
    required this.siteId,
    this.configuration = const {},
  });
  final String deviceId;
  final IotTransport transport;
  final String siteId;
  final Map<String, Object?> configuration;
}

class DeviceCommand {
  const DeviceCommand({
    required this.deviceId,
    required this.name,
    this.arguments = const {},
    this.requiresExplicitConfirmation = true,
  });
  final String deviceId;
  final String name;
  final Map<String, Object?> arguments;
  final bool requiresExplicitConfirmation;
}

class DeviceReading {
  const DeviceReading(
      {required this.deviceId, required this.label, required this.at});
  final String deviceId;
  final String label;
  final DateTime at;
}
