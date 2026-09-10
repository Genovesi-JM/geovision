import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/storage/local_store.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/account/data/customer_experience_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _ExperienceAdapter implements HttpClientAdapter {
  final headers = <String?>[];

  ResponseBody _json(int status, Map<String, Object?> body) =>
      ResponseBody.fromString(
        jsonEncode(body),
        status,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    final workspaceId = options.headers['X-Workspace-ID']?.toString();
    headers.add(workspaceId);
    if (workspaceId == 'revoked-workspace' || workspaceId == 'denied') {
      return _json(403, {'detail': 'Workspace is not accessible'});
    }
    return _json(200, {
      'active_workspace_id': 'default-workspace',
      'active_organization_id': 'organization-1',
      'permissions': ['asset:read'],
      'capabilities': ['assets'],
      'workspaces': [
        {
          'id': 'default-workspace',
          'organization_id': 'organization-1',
          'name': 'Default',
          'organization_name': 'Customer',
          'role': 'member',
          'sector': 'AGRICULTURE',
          'sectors': ['AGRICULTURE', 'mining'],
          'modules_enabled': ['assets'],
        },
      ],
    });
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('revoked persisted workspace is cleared and default retried once',
      () async {
    final prefs = await SharedPreferences.getInstance();
    final store = LocalStore(prefs);
    await store.writeJson(
      'customer_workspace_selection',
      {'workspace_id': 'revoked-workspace'},
    );
    final adapter = _ExperienceAdapter();
    final client = _client(adapter);
    final repository = CustomerExperienceRepository(client, store, _config);

    final experience = await repository.load();

    expect(adapter.headers, ['revoked-workspace', null]);
    expect(experience.activeWorkspaceId, 'default-workspace');
    expect(experience.activeWorkspace?.sector, 'agriculture');
    expect(experience.activeWorkspace?.sectors, ['agriculture', 'mining']);
    expect(client.workspaceId, 'default-workspace');
    expect(
      store.readJson('customer_workspace_selection')?.data['workspace_id'],
      'default-workspace',
    );
  });

  test('explicit denied selection restores the previous request header',
      () async {
    final prefs = await SharedPreferences.getInstance();
    final store = LocalStore(prefs);
    final adapter = _ExperienceAdapter();
    final client = _client(adapter)..selectWorkspace('previous-workspace');
    final repository = CustomerExperienceRepository(client, store, _config);

    await expectLater(
      repository.select('denied'),
      throwsA(isA<CustomerExperienceException>()),
    );

    expect(client.workspaceId, 'previous-workspace');
    expect(adapter.headers, ['denied']);
  });
}

ApiClient _client(HttpClientAdapter adapter) {
  final dio = Dio()..httpClientAdapter = adapter;
  return ApiClient(
    config: _config,
    tokenStore: SecureTokenStore(const FlutterSecureStorage()),
    dio: dio,
  );
}

const _config = AppConfig(
  flavor: AppFlavor.dev,
  apiBaseUrl: 'https://api.example.test',
  demoMode: false,
  connectTimeout: Duration(seconds: 1),
  receiveTimeout: Duration(seconds: 1),
  mapProvider: 'demo',
  paymentProvider: 'mock',
  pushProvider: 'mock',
  enableBiometricUnlock: false,
);
