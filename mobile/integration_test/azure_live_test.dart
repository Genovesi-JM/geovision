// Opt-in acceptance test for the existing Azure synthetic QA account.
// Credentials are read at runtime from a private file; never embed them in a build.
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/routing/app_router.dart';
import 'package:geovision/features/account/data/customer_experience_repository.dart';
import 'package:geovision/features/assets/data/assets_repository.dart';
import 'package:geovision/features/assets/presentation/assets_screen.dart';
import 'package:geovision/features/authentication/presentation/auth_controller.dart';
import 'package:geovision/features/authentication/presentation/login_screen.dart';
import 'package:geovision/features/home/data/home_repository.dart';

Future<void> until(WidgetTester tester, bool Function() ready) async {
  final deadline = DateTime.now().add(const Duration(seconds: 75));
  while (!ready() && DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 200));
  }
  expect(ready(), isTrue, reason: 'Live screen did not become ready');
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  const credentialsPath = String.fromEnvironment('GV_QA_CREDENTIALS_PATH');
  testWidgets(
      'Azure: existing login, workspace, home, assets, logout and login',
      (tester) async {
    final config = AppConfig.fromEnvironment();
    expect(config.demoMode, isFalse);
    expect(Uri.parse(config.apiBaseUrl).scheme, 'https');
    final account = jsonDecode(await File(credentialsPath).readAsString())
        as Map<String, dynamic>;
    SharedPreferences.setMockInitialValues({});
    // Isolated test storage; do not overwrite an owner's simulator login.
    FlutterSecureStorage.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final container = ProviderContainer(overrides: [
      appConfigProvider.overrideWithValue(config),
      sharedPrefsProvider.overrideWithValue(prefs),
    ]);
    addTearDown(container.dispose);
    container.read(apiClientProvider).raw.interceptors.add(InterceptorsWrapper(
      onError: (error, handler) {
        // Deliberately omit headers, request bodies and server response bodies.
        debugPrint('Live API failure: ${error.requestOptions.path} '
            '${error.type.name} HTTP ${error.response?.statusCode}');
        handler.next(error);
      },
    ));
    final health = await container.read(apiClientProvider).raw.get('/health');
    expect(health.statusCode, 200);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const GeoVisionApp(),
    ));
    Future<void> login() async {
      await until(tester, () => find.byType(LoginScreen).evaluate().isNotEmpty);
      await tester.enterText(
          find.byType(TextFormField).at(0), account['email']);
      await tester.enterText(
          find.byType(TextFormField).at(1), account['password']);
      await tester.ensureVisible(find.byType(FilledButton).first);
      await tester.tap(find.byType(FilledButton).first);
      await until(
          tester, () => container.read(authControllerProvider).isSignedIn);
      await until(tester, () => container.read(homeSummaryProvider).hasValue);
      final experience =
          await container.read(customerExperienceProvider.future);
      expect(experience.activeWorkspaceId == account['workspace_id'], isTrue);
      expect(
          container.read(homeSummaryProvider).value!.workspaceId ==
              account['workspace_id'],
          isTrue);
    }

    await login();
    container.read(routerProvider).go('/assets');
    await until(
        tester,
        () =>
            find.byType(AssetsScreen).evaluate().isNotEmpty &&
            container.read(customerAssetsProvider).hasValue);
    final assets = await container.read(customerAssetsProvider.future);
    expect(assets.fromCache, isFalse);
    expect(
        assets.value.any((asset) => asset.id == account['asset_id']), isTrue);
    expect(find.text('QA Azure Journey — Synthetic Site'), findsWidgets);
    container
        .read(routerProvider)
        .go('/work/new?asset_id=${account['asset_id']}');
    await until(tester,
        () => find.byType(DropdownButton<String>).evaluate().isNotEmpty);
    expect(
        tester
            .widget<DropdownButton<String>>(find.byType(DropdownButton<String>))
            .value,
        account['asset_id']);

    await container.read(authControllerProvider.notifier).logout();
    await until(tester, () => find.byType(LoginScreen).evaluate().isNotEmpty);
    expect(await container.read(secureTokenStoreProvider).readAccess(), isNull);
    await login();
    await container.read(authControllerProvider.notifier).logout();
    await tester.pumpWidget(const SizedBox.shrink());
  }, skip: credentialsPath.isEmpty);
}
