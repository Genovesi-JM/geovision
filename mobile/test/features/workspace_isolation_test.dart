import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/networking/connectivity_service.dart';
import 'package:geovision/core/storage/local_store.dart';
import 'package:geovision/core/storage/offline_queue.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/assets/data/assets_repository.dart';
import 'package:geovision/features/orders/data/orders_repository.dart';
import 'package:geovision/features/work/data/work_repository.dart';
import 'package:geovision/features/work/domain/service_request.dart';
import 'package:geovision/integrations/payments/mock_payment_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _OfflineConnectivity extends ConnectivityService {
  @override
  Future<bool> get isOnline async => false;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
  });

  test('offline service requests are visible only in their source workspace',
      () async {
    final prefs = await SharedPreferences.getInstance();
    final queue = OfflineQueue(prefs);
    await queue.enqueue(
        'service_request', _request('request-a', 'workspace-a'));
    await queue.enqueue(
        'service_request', _request('request-b', 'workspace-b'));
    await queue.enqueue('service_request', _request('legacy', null));
    final client = _client()..selectWorkspace('workspace-a');
    final repository = WorkRepository(
      client,
      queue,
      _OfflineConnectivity(),
      _config,
    );

    expect(
      (await repository.getRequests()).map((request) => request.id),
      ['request-a'],
    );

    client.selectWorkspace('workspace-b');
    expect(
      (await repository.getRequests()).map((request) => request.id),
      ['request-b'],
    );
  });

  test('new offline requests carry the selected workspace id', () async {
    final prefs = await SharedPreferences.getInstance();
    final queue = OfflineQueue(prefs);
    final client = _client()..selectWorkspace('workspace-a');
    final repository = WorkRepository(
      client,
      queue,
      _OfflineConnectivity(),
      _config,
    );

    await repository.submit(
      type: ServiceType.inspection,
      siteId: 'asset-a',
      siteName: 'Asset A',
      urgency: 'normal',
      description: 'Inspect this asset',
    );

    expect(queue.readAll().single.payload['workspace_id'], 'workspace-a');
  });

  test('asset cache and cart identifiers are partitioned by workspace',
      () async {
    final prefs = await SharedPreferences.getInstance();
    final store = LocalStore(prefs);
    await store.writeJson('canonical_assets::workspace-a', [
      _asset('asset-a'),
    ]);
    await store.writeJson('canonical_assets::workspace-b', [
      _asset('asset-b'),
    ]);
    final client = _client()..selectWorkspace('workspace-a');
    final assets = AssetsRepository(
      client,
      store,
      _OfflineConnectivity(),
      _config,
    );
    final orders = OrdersRepository(
      api: client,
      config: _config,
      payments: const MockPaymentProvider(),
      preferences: prefs,
    );

    expect((await assets.list()).value.single.id, 'asset-a');
    final cartA = orders.cartId;

    client.selectWorkspace('workspace-b');
    expect((await assets.list()).value.single.id, 'asset-b');
    final cartB = orders.cartId;
    expect(cartB, isNot(cartA));

    client.selectWorkspace('workspace-a');
    expect(orders.cartId, cartA);
  });
}

Map<String, dynamic> _request(String id, String? workspaceId) => {
      'id': id,
      'type': 'inspection',
      'site_id': 'asset-1',
      'site_name': 'Asset',
      'urgency': 'normal',
      'description': 'Inspect',
      'status': 'submitted',
      'created_at': '2026-09-10T12:00:00Z',
      if (workspaceId != null) 'workspace_id': workspaceId,
    };

Map<String, dynamic> _asset(String id) => {
      'id': id,
      'name': id,
      'sector': 'AGRICULTURE',
      'asset_type': 'FIELD',
      'status': 'active',
      'metadata': <String, dynamic>{},
    };

ApiClient _client() => ApiClient(
      config: _config,
      tokenStore: SecureTokenStore(const FlutterSecureStorage()),
      dio: Dio(),
    );

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
