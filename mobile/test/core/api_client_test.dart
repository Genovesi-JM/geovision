import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/storage/secure_token_store.dart';

class _Concurrent401Adapter implements HttpClientAdapter {
  int oldTokenRequests = 0;
  int replayedRequests = 0;
  int refreshRequests = 0;
  final Completer<void> _bothOldRequestsArrived = Completer<void>();

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
    if (options.path == '/auth/refresh') {
      refreshRequests += 1;
      return _json(200, {
        'access_token': 'new-access',
        'refresh_token': 'new-refresh',
      });
    }

    if (options.headers['Authorization'] == 'Bearer old-access') {
      oldTokenRequests += 1;
      if (oldTokenRequests == 2) _bothOldRequestsArrived.complete();
      await _bothOldRequestsArrived.future;
      return _json(401, {'detail': 'expired'});
    }

    expect(options.headers['Authorization'], 'Bearer new-access');
    replayedRequests += 1;
    return _json(200, {'ok': true});
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('concurrent 401 responses share one rotating refresh', () async {
    FlutterSecureStorage.setMockInitialValues({
      'gv_access_token': 'old-access',
      'gv_refresh_token': 'old-refresh',
    });
    final adapter = _Concurrent401Adapter();
    final protectedDio = Dio()..httpClientAdapter = adapter;
    final refreshDio = Dio()..httpClientAdapter = adapter;
    final tokens = SecureTokenStore(const FlutterSecureStorage());
    final client = ApiClient(
      config: const AppConfig(
        flavor: AppFlavor.dev,
        apiBaseUrl: 'https://api.example.test',
        demoMode: false,
        connectTimeout: Duration(seconds: 1),
        receiveTimeout: Duration(seconds: 1),
        mapProvider: 'demo',
        paymentProvider: 'mock',
        pushProvider: 'mock',
        enableBiometricUnlock: false,
      ),
      tokenStore: tokens,
      dio: protectedDio,
      refreshDio: refreshDio,
    );

    final responses = await Future.wait([
      client.raw.get('/first'),
      client.raw.get('/second'),
    ]);

    expect(responses.map((response) => response.statusCode), everyElement(200));
    expect(adapter.oldTokenRequests, 2);
    expect(adapter.replayedRequests, 2);
    expect(adapter.refreshRequests, 1);
    expect(await tokens.readAccess(), 'new-access');
    expect(await tokens.readRefresh(), 'new-refresh');
  });
}
