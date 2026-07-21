import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../integrations/iot/iot_provider.dart';
import '../domain/device.dart';

class DevicesRepository {
  DevicesRepository(this._iot);
  final IotProvider _iot;
  Future<List<GvDevice>> getDevices() => _iot.fetchDevices();
  Future<IotOperationResult> diagnose(String deviceId) =>
      _iot.diagnose(deviceId);
  Future<IotOperationResult> provision(DeviceProvisioningRequest request) =>
      _iot.provision(request);
  Future<IotOperationResult> sendCommand(DeviceCommand command) =>
      _iot.sendCommand(command);
  String get providerId => _iot.id;
}

final devicesRepositoryProvider = Provider<DevicesRepository>(
    (ref) => DevicesRepository(ref.watch(iotProviderProvider)));
final devicesProvider = FutureProvider<List<GvDevice>>(
    (ref) => ref.watch(devicesRepositoryProvider).getDevices());
