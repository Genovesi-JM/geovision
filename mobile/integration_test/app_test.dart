import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'Critical journey: launch → Portal → My assets → Alerts → Marketplace → More',
      (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    const config = AppConfig(
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

    await tester.pumpWidget(ProviderScope(
      overrides: [
        appConfigProvider.overrideWithValue(config),
        sharedPrefsProvider.overrideWithValue(prefs),
      ],
      child: const GeoVisionApp(),
    ));
    await tester.pumpAndSettle(const Duration(seconds: 2));

    // Portal (Home) renders the demo organisation.
    expect(find.text('Fazenda Kilombo Agro'), findsWidgets);

    // My assets → sites list (route /sites).
    await tester.tap(find.text('My assets').last);
    await tester.pumpAndSettle();
    expect(find.text('Kilombo North Fields'), findsWidgets);

    // Alerts → IoT alert console (route /alerts).
    await tester.tap(find.text('Alerts').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('Irrigation'), findsWidgets);

    // Marketplace → store (route /orders).
    await tester.tap(find.text('Marketplace').last);
    await tester.pumpAndSettle();
    expect(find.text('GeoVision Marketplace'), findsWidgets);

    // More → account (route /account).
    await tester.tap(find.text('More').last);
    await tester.pumpAndSettle();
    expect(find.text('Sign out'), findsWidgets);
  });
}
