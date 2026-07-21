import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('GeoVision demo opens the customer home', (tester) async {
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

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appConfigProvider.overrideWithValue(config),
          sharedPrefsProvider.overrideWithValue(prefs),
        ],
        child: const GeoVisionApp(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Fazenda Kilombo Agro'), findsWidgets);
    expect(find.text('Home'), findsWidgets);
    expect(find.text('Sites'), findsWidgets);
    expect(find.text('Alerts'), findsWidgets);
    expect(find.text('Work'), findsWidgets);
    expect(find.text('Request'), findsWidgets);
    expect(find.text('Store'), findsWidgets);
    expect(find.text('Account'), findsWidgets);

    await tester.tap(find.text('Store').last);
    await tester.pumpAndSettle();
    expect(find.text('GeoVision Store'), findsOneWidget);
    expect(find.text('Análise NDVI/NDRE de culturas'), findsOneWidget);
    expect(find.text('AKZ'), findsOneWidget);
  });
}
