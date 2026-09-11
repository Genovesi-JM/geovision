import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _demoConfig = AppConfig(
  flavor: AppFlavor.dev,
  apiBaseUrl: 'http://127.0.0.1:8010',
  demoMode: true,
  connectTimeout: Duration(seconds: 5),
  receiveTimeout: Duration(seconds: 5),
  mapProvider: 'demo',
  paymentProvider: 'mock',
  pushProvider: 'mock',
  enableBiometricUnlock: false,
);

void main() {
  final devices = <String, Size>{
    'compact iPhone': const Size(320, 568),
    'standard iPhone': const Size(393, 852),
    'compact Android': const Size(360, 640),
    'standard Android': const Size(412, 915),
  };

  for (final device in devices.entries) {
    testWidgets('${device.key} keeps primary destinations inside the viewport',
        (tester) async {
      tester.view
        ..physicalSize = device.value
        ..devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      SharedPreferences.setMockInitialValues({'gv_preferred_language': 'es'});
      final prefs = await SharedPreferences.getInstance();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appConfigProvider.overrideWithValue(_demoConfig),
            sharedPrefsProvider.overrideWithValue(prefs),
          ],
          child: const GeoVisionApp(),
        ),
      );
      await tester.pumpAndSettle();
      _expectNoLayoutFailure(tester, '${device.key} Inicio');

      for (final destination in ['Activos', 'Acciones', 'Servicios', 'Más']) {
        await tester.tap(find.text(destination).last);
        await tester.pumpAndSettle();
        _expectNoLayoutFailure(tester, '${device.key} $destination');
        expect(
          tester.getBottomRight(find.byType(Scaffold).last).dx,
          lessThanOrEqualTo(device.value.width),
        );
      }
    });
  }
}

void _expectNoLayoutFailure(WidgetTester tester, String label) {
  final exception = tester.takeException();
  expect(exception, isNull, reason: '$label produced a layout exception');
}
