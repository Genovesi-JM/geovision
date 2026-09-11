import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/routing/app_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  testWidgets('GeoVision demo exposes exactly five customer destinations',
      (tester) async {
    SharedPreferences.setMockInitialValues({'gv_preferred_language': 'en'});
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

    expect(find.text('GeoVision España Demo'), findsWidgets);
    expect(find.text('Home'), findsWidgets);
    expect(find.text('Assets'), findsOneWidget);
    expect(find.text('Actions'), findsOneWidget);
    expect(find.text('Services'), findsOneWidget);
    expect(find.text('More'), findsWidgets);

    await tester.tap(find.text('Services').last);
    await tester.pumpAndSettle();
    expect(find.text('Services'), findsWidgets);
    expect(find.text('Essential Aerial Mapping'), findsOneWidget);

    await tester.tap(find.text('More').last);
    await tester.pumpAndSettle();
    expect(find.text('More'), findsWidgets);
    expect(find.text('Reports'), findsOneWidget);
    expect(find.text('Devices'), findsOneWidget);
    expect(find.text('Billing'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.textContaining('seller', findRichText: true), findsNothing);
    expect(find.textContaining('provider', findRichText: true), findsNothing);

    await tester.tap(find.text('Assets').last);
    await tester.pumpAndSettle();
    expect(find.text('Reserva del Humedal de Doñana'), findsOneWidget);
    expect(find.text('Acopio Minero A'), findsOneWidget);
  });

  testWidgets('legacy deep links preserve their exact target identifiers',
      (tester) async {
    SharedPreferences.setMockInitialValues({'gv_preferred_language': 'en'});
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
    final container = ProviderContainer(
      overrides: [
        appConfigProvider.overrideWithValue(config),
        sharedPrefsProvider.overrideWithValue(prefs),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const GeoVisionApp(),
      ),
    );
    await tester.pumpAndSettle();
    final router = container.read(routerProvider);

    router.go('/sites/site-1');
    await tester.pumpAndSettle();
    expect(router.routeInformationProvider.value.uri.path, '/assets/site-1');
    expect(find.text('Finca Madrid Norte'), findsOneWidget);

    router.go('/orders/or-1');
    await tester.pumpAndSettle();
    expect(
      router.routeInformationProvider.value.uri.path,
      '/services/orders/or-1',
    );
    expect(find.text('OR-1'), findsOneWidget);

    router.go('/alerts/al-1');
    await tester.pumpAndSettle();
    expect(router.routeInformationProvider.value.uri.path, '/alerts/al-1');
    expect(find.text('Irrigation failure — Block A'), findsOneWidget);
  });

  testWidgets('workspace switch refreshes customer-visible asset context',
      (tester) async {
    SharedPreferences.setMockInitialValues({'gv_preferred_language': 'en'});
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

    await tester.tap(find.text('GeoVision España Demo · Finca Madrid Norte'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Infraestructuras Madrid'));
    await tester.pumpAndSettle();
    expect(
      find.text('GeoVision España Demo · Infraestructuras Madrid'),
      findsOneWidget,
    );

    await tester.tap(find.text('Assets').last);
    await tester.pumpAndSettle();
    expect(find.text('Madrid M-30 — Tramo 4'), findsOneWidget);
    expect(find.text('Reserva del Humedal de Doñana'), findsNothing);
  });
}
