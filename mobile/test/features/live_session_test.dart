import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/errors/result.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/networking/connectivity_service.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/account/data/customer_experience_repository.dart';
import 'package:geovision/features/assistant/data/gaia_repository.dart';
import 'package:geovision/features/authentication/data/auth_repository.dart';
import 'package:geovision/features/authentication/domain/auth_session.dart';
import 'package:geovision/features/authentication/presentation/auth_controller.dart';

import '../core/live_provider_selection_test.dart' show config;

class _Online extends ConnectivityService {
  @override
  Future<bool> get isOnline async => true;
}

class _Auth extends AuthRepository {
  _Auth(ApiClient api, SecureTokenStore tokens)
      : super(api: api, tokenStore: tokens, config: config(false));
  @override
  Future<AuthSession> restoreSession() async => AuthSession.unauthenticated;
  @override
  Future<Result<AuthSession>> login(String email, String password) async =>
      const Ok(AuthSession(mode: AuthMode.authenticated));
  @override
  Future<void> logout() async {}
}

class _Adapter implements HttpClientAdapter {
  int membershipLoads = 0;
  String? context;
  final paths = <String>[];
  @override
  Future<ResponseBody> fetch(RequestOptions options,
      Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    paths.add(options.path);
    Object body;
    switch (options.path) {
      case '/mobile/experience':
        membershipLoads++;
        body = {
          'active_workspace_id': 'workspace-1',
          'active_organization_id': 'org-1',
          'permissions': ['asset:read'],
          'capabilities': ['assets'],
          'workspaces': [
            {'id': 'workspace-1', 'organization_id': 'org-1', 'name': 'Test'}
          ],
        };
      case '/assets':
        body = [
          {
            'id': 'canonical-only',
            'name': 'Web-created field',
            'asset_type': 'FARM'
          }
        ];
      case '/kpi/alerts':
        body = {'alerts': []};
      case '/mobile/devices':
        body = {'items': []};
      case '/mobile/sites':
      case '/mobile/service-requests':
      case '/shop/products':
        body = [];
      case '/ai/chat':
        context = (options.data as Map)['page_text'] as String;
        body = {'reply': 'There is one field.'};
      default:
        throw StateError('Unexpected route ${options.path}');
    }
    return ResponseBody.fromString(jsonEncode(body), 200, headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType]
    });
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ProviderContainer container;
  late _Adapter adapter;
  late ApiClient api;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final tokens = SecureTokenStore(const FlutterSecureStorage());
    adapter = _Adapter();
    api = ApiClient(
        config: config(false),
        tokenStore: tokens,
        dio: Dio()..httpClientAdapter = adapter);
    container = ProviderContainer(overrides: [
      appConfigProvider.overrideWithValue(config(false)),
      sharedPrefsProvider.overrideWithValue(prefs),
      apiClientProvider.overrideWithValue(api),
      authRepositoryProvider.overrideWithValue(_Auth(api, tokens)),
      connectivityServiceProvider.overrideWithValue(_Online()),
    ]);
    container.read(authControllerProvider);
    await Future<void>.delayed(Duration.zero);
  });
  tearDown(() => container.dispose());

  test('logout drops workspace data and a new login reloads membership',
      () async {
    await expectLater(container.read(customerExperienceProvider.future),
        throwsA(isA<CustomerExperienceException>()));
    expect(adapter.membershipLoads, 0);
    final auth = container.read(authControllerProvider.notifier);
    await auth.login('test@example.test', 'unused');
    final first = await container.read(customerExperienceProvider.future);
    expect(api.workspaceId, 'workspace-1');
    await auth.logout();
    await expectLater(container.read(customerExperienceProvider.future),
        throwsA(isA<CustomerExperienceException>()));
    expect(api.workspaceId, isNull);
    await auth.login('test@example.test', 'unused');
    final second = await container.read(customerExperienceProvider.future);
    expect(identical(first, second), isFalse);
    expect(adapter.membershipLoads, 2);
  });

  test('GAIA includes canonical assets when the legacy sites list is empty',
      () async {
    await container
        .read(authControllerProvider.notifier)
        .login('test@example.test', 'unused');
    final reply = await container.read(gaiaRepositoryProvider).send(
        [const GaiaMessage(role: 'user', content: 'What assets do I have?')]);
    expect(reply, 'There is one field.');
    expect(adapter.paths, contains('/assets'));
    expect(adapter.context, contains('Totals: 1 assets'));
    expect(adapter.context, contains('Selected asset: Web-created field'));
    expect(adapter.context, isNot(contains('Totals: 0 sites')));
  });
}
