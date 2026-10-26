import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/errors/result.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/routing/app_router.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/authentication/data/auth_repository.dart';
import 'package:geovision/features/authentication/domain/auth_session.dart';
import 'package:geovision/features/authentication/domain/registration_request.dart';
import 'package:geovision/features/authentication/presentation/auth_controller.dart';
import 'package:geovision/features/authentication/presentation/reset_password_screen.dart';
import '../core/live_provider_selection_test.dart' show config;

class _Auth extends AuthRepository {
  _Auth()
      : super(
            api:
                ApiClient(config: config(true), tokenStore: SecureTokenStore()),
            tokenStore: SecureTokenStore(),
            config: config(true));
  @override
  Future<AuthSession> restoreSession() async => AuthSession.unauthenticated;
  @override
  Future<Result<AuthSession>> register(RegistrationRequest request) async =>
      const Ok(AuthSession(mode: AuthMode.authenticated));
}

void main() {
  Future<ProviderContainer> mount(WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({'gv_preferred_language': 'en'});
    FlutterSecureStorage.setMockInitialValues({});
    final container = ProviderContainer(overrides: [
      appConfigProvider.overrideWithValue(config(true)),
      sharedPrefsProvider
          .overrideWithValue(await SharedPreferences.getInstance()),
      authControllerProvider
          .overrideWith((ref) => AuthController(_Auth(), demoMode: false)),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
        container: container, child: const GeoVisionApp()));
    await tester.pumpAndSettle();
    return container;
  }

  testWidgets('password reset remains reachable without a login',
      (tester) async {
    final container = await mount(tester);
    container.read(routerProvider).go('/reset-password?token=synthetic');
    await tester.pumpAndSettle();
    expect(find.byType(ResetPasswordScreen), findsOneWidget);
    expect(container.read(authControllerProvider).isSignedIn, isFalse);
  });
  for (final entry in {
    'Request a service': '/work/new',
    'Monitor an asset': '/assets?setup=monitoring',
    'Buy a product': '/services/shop',
    'View an invitation': '/invitation/accept',
  }.entries) {
    testWidgets('registration opens the chosen journey: ${entry.key}',
        (tester) async {
      final container = await mount(tester);
      final router = container.read(routerProvider);
      router.go('/register');
      await tester.pumpAndSettle();
      await tester.enterText(
          find.byType(TextFormField).at(0), 'Synthetic Test');
      await tester.enterText(
          find.byType(TextFormField).at(1), 'synthetic@example.com');
      Future<void> advance() async {
        await tester.ensureVisible(find.byType(FilledButton).first);
        await tester.tap(find.byType(FilledButton).first);
        await tester.pumpAndSettle();
      }

      await advance();
      await tester.enterText(
          find.byType(TextFormField).at(0), 'Synthetic-password-9');
      await tester.enterText(
          find.byType(TextFormField).at(1), 'Synthetic-password-9');
      await advance();
      await tester.ensureVisible(find.text(entry.key));
      await tester.tap(find.text(entry.key));
      await tester.pumpAndSettle();
      await advance();
      expect(identical(container.read(routerProvider), router), isTrue);
      expect(router.routeInformationProvider.value.uri.toString(), entry.value);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}
