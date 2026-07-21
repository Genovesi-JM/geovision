import 'dart:async';
import '../../core/demo/demo_data.dart';
import '../../features/devices/domain/device.dart';
import 'iot_provider.dart';

class MockIotProvider implements IotProvider {
  const MockIotProvider();
  @override
  String get id => 'mock';
  @override
  bool get requiresCredentials => false;
  @override
  Set<IotTransport> get supportedTransports => IotTransport.values.toSet();
  @override
  Future<List<GvDevice>> fetchDevices() async => DemoData.devices();
  @override
  Stream<DeviceReading> subscribeReadings(String deviceId) async* {
    var i = 0;
    while (i < 3) {
      await Future<void>.delayed(const Duration(seconds: 2));
      yield DeviceReading(
          deviceId: deviceId, label: 'Reading ${++i}', at: DateTime.now());
    }
  }

  @override
  Future<IotOperationResult> diagnose(String deviceId) async {
    final device =
        DemoData.devices().where((item) => item.id == deviceId).firstOrNull;
    if (device == null) {
      return const IotOperationResult(IotOutcome.unsupported,
          message: 'Device is not registered.');
    }
    return switch (device.status) {
      'online' => const IotOperationResult(IotOutcome.success,
          message: 'Telemetry and cloud route are operational.'),
      'offline' => const IotOperationResult(IotOutcome.offline,
          message: 'No recent heartbeat.', retryable: true),
      'pairing' => const IotOperationResult(IotOutcome.pending,
          message: 'Provisioning is still in progress.', retryable: true),
      'credentials_required' => const IotOperationResult(
          IotOutcome.credentialsRequired,
          message: 'Vendor credentials are required.'),
      'unsupported' => const IotOperationResult(IotOutcome.unsupported,
          message: 'No compatible protocol is available.'),
      'error' => const IotOperationResult(IotOutcome.error,
          message: 'The provider returned an integration error.',
          retryable: true),
      _ => const IotOperationResult(IotOutcome.pending,
          message: 'Maintenance or review is required.'),
    };
  }

  @override
  Future<IotOperationResult> provision(
      DeviceProvisioningRequest request) async {
    if (!supportedTransports.contains(request.transport)) {
      return const IotOperationResult(IotOutcome.unsupported);
    }
    if (request.transport == IotTransport.bluetooth &&
        request.configuration['permissionGranted'] != true) {
      return const IotOperationResult(IotOutcome.permissionRequired,
          message: 'Bluetooth permission is required.', retryable: true);
    }
    return const IotOperationResult(IotOutcome.success,
        message: 'Demo device provisioned.');
  }

  @override
  Future<IotOperationResult> sendCommand(DeviceCommand command) async {
    final diagnosis = await diagnose(command.deviceId);
    if (!diagnosis.succeeded) return diagnosis;
    if (command.requiresExplicitConfirmation &&
        command.arguments['confirmed'] != true) {
      return const IotOperationResult(IotOutcome.rejected,
          message: 'Explicit confirmation is required.');
    }
    return const IotOperationResult(IotOutcome.success,
        message: 'Demo command accepted.');
  }
}
