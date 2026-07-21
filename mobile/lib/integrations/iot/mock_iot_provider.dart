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
}
