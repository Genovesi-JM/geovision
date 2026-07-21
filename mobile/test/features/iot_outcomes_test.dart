import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/integrations/iot/iot_provider.dart';
import 'package:geovision/integrations/iot/mock_iot_provider.dart';

void main() {
  const provider = MockIotProvider();

  test('diagnostics expose success and every recoverable integration outcome',
      () async {
    expect((await provider.diagnose('dv-1')).outcome, IotOutcome.success);
    expect((await provider.diagnose('dv-3')).outcome, IotOutcome.offline);
    expect((await provider.diagnose('dv-5')).outcome, IotOutcome.pending);
    expect((await provider.diagnose('dv-6')).outcome,
        IotOutcome.credentialsRequired);
    expect((await provider.diagnose('dv-7')).outcome, IotOutcome.unsupported);
    expect((await provider.diagnose('dv-8')).outcome, IotOutcome.error);
  });

  test('BLE provisioning requires permission before succeeding', () async {
    const blocked = DeviceProvisioningRequest(
      deviceId: 'dv-5',
      transport: IotTransport.bluetooth,
      siteId: 'site-1',
    );
    expect((await provider.provision(blocked)).outcome,
        IotOutcome.permissionRequired);

    const allowed = DeviceProvisioningRequest(
      deviceId: 'dv-5',
      transport: IotTransport.bluetooth,
      siteId: 'site-1',
      configuration: {'permissionGranted': true},
    );
    expect((await provider.provision(allowed)).succeeded, isTrue);
  });

  test('remote commands require explicit customer confirmation', () async {
    const unconfirmed = DeviceCommand(deviceId: 'dv-1', name: 'calibrate');
    expect(
        (await provider.sendCommand(unconfirmed)).outcome, IotOutcome.rejected);

    const confirmed = DeviceCommand(
      deviceId: 'dv-1',
      name: 'calibrate',
      arguments: {'confirmed': true},
    );
    expect((await provider.sendCommand(confirmed)).succeeded, isTrue);
  });
}
