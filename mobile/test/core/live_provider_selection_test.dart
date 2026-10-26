import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/integrations/iot/backend_iot_provider.dart';
import 'package:geovision/integrations/iot/mock_iot_provider.dart';

AppConfig config(bool demo) => AppConfig(
      flavor: AppFlavor.staging,
      apiBaseUrl: 'https://api.example.test',
      demoMode: demo,
      connectTimeout: const Duration(seconds: 5),
      receiveTimeout: const Duration(seconds: 5),
      mapProvider: 'openstreetmap',
      paymentProvider: 'mock',
      pushProvider: 'mock',
      enableBiometricUnlock: false,
    );

void main() {
  test('live mode uses the real device API and cannot approve mock payments',
      () async {
    final container = ProviderContainer(overrides: [
      appConfigProvider.overrideWithValue(config(false)),
    ]);
    addTearDown(container.dispose);
    expect(container.read(iotProviderProvider), isA<BackendIotProvider>());
    final payment = await container.read(paymentProviderProvider).createIntent(
          amountCents: 100,
          currency: 'EUR',
          orderId: 'test-order',
        );
    expect(payment.status, 'failed');
    expect(payment.reference, isEmpty);
  });

  test('demo mode retains its explicit simulated providers', () {
    final container = ProviderContainer(overrides: [
      appConfigProvider.overrideWithValue(config(true)),
    ]);
    addTearDown(container.dispose);
    expect(container.read(iotProviderProvider), isA<MockIotProvider>());
    expect(container.read(paymentProviderProvider).id, 'mock');
  });
}
