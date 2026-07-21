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

  testWidgets('Critical journey: launch → demo → home → sites → alerts → work',
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

    // Home renders the demo organisation.
    expect(find.text('Fazenda Kilombo Agro'), findsWidgets);

    // Navigate to Sites.
    await tester.tap(find.text('Sites').last);
    await tester.pumpAndSettle();
    expect(find.text('Kilombo North Fields'), findsWidgets);

    // Navigate to Alerts.
    await tester.tap(find.text('Alerts').last);
    await tester.pumpAndSettle();
    expect(find.textContaining('Irrigation'), findsWidgets);

    // Navigate to Work.
    await tester.tap(find.text('Work').last);
    await tester.pumpAndSettle();
    expect(find.text('New request'), findsWidgets);
  });
}
