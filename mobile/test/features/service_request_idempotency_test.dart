import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/networking/connectivity_service.dart';
import 'package:geovision/core/storage/offline_queue.dart';
import 'package:geovision/core/storage/offline_sync_service.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/work/data/work_repository.dart';
import 'package:geovision/features/work/domain/service_request.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _OnlineConnectivity extends ConnectivityService {
  @override
  Future<bool> get isOnline async => true;
}

class _LostResponseThenReplayAdapter implements HttpClientAdapter {
  final idempotencyKeys = <String>[];
  var requests = 0;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    expect(options.path, '/mobile/service-requests');
    idempotencyKeys.add(options.headers['Idempotency-Key'] as String);
    requests += 1;
    if (requests == 1) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionError,
        error: 'response lost after commit',
      );
    }
    return ResponseBody.fromString(
      jsonEncode({'accepted': true}),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
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

  test('lost response and offline replay reuse one service idempotency key',
      () async {
    final adapter = _LostResponseThenReplayAdapter();
    final dio = Dio()..httpClientAdapter = adapter;
    final client = ApiClient(
      config: _config,
      tokenStore: SecureTokenStore(const FlutterSecureStorage()),
      dio: dio,
    )..selectWorkspace('workspace-a');
    final queue = OfflineQueue(await SharedPreferences.getInstance());
    final repository = WorkRepository(
      client,
      queue,
      _OnlineConnectivity(),
      _config,
    );

    final pending = await repository.submit(
      type: ServiceType.inspection,
      siteId: 'asset-a',
      siteName: 'Asset A',
      urgency: 'normal',
      description: 'Inspect this asset without duplicating the request.',
    );
    expect(pending.pendingSync, isTrue);
    expect(queue.pendingCount, 1);

    final result = await OfflineSyncService(queue, client, _config).syncNow();
    expect(result.synced, 1);
    expect(result.failed, 0);
    expect(result.remaining, 0);
    expect(adapter.idempotencyKeys, hasLength(2));
    expect(adapter.idempotencyKeys[0], adapter.idempotencyKeys[1]);
    expect(adapter.idempotencyKeys.first, startsWith('mobile-'));
  });
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
