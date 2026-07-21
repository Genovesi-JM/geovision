import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../integrations/iot/iot_provider.dart';
import '../domain/device.dart';

class DevicesRepository {
  DevicesRepository(this._iot);
  final IotProvider _iot;
  Future<List<GvDevice>> getDevices() => _iot.fetchDevices();
}

final devicesRepositoryProvider = Provider<DevicesRepository>(
    (ref) => DevicesRepository(ref.watch(iotProviderProvider)));
final devicesProvider = FutureProvider<List<GvDevice>>(
    (ref) => ref.watch(devicesRepositoryProvider).getDevices());
