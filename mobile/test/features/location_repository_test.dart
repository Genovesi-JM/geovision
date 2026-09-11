import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/sites/data/location_repository.dart';

class _LocationAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    final body = switch (options.path) {
      '/location/places:autocomplete' => {
          'provider': 'google_maps',
          'simulated': false,
          'suggestions': [
            {
              'provider_reference': 'place-1',
              'primary_text': 'Madrid',
              'secondary_text': 'Community of Madrid, Spain',
            },
          ],
        },
      '/location/places:resolve' => {
          'provider': 'google_maps',
          'simulated': false,
          'provider_reference': 'place-1',
          'display_name': 'Madrid',
          'formatted_address': 'Madrid, Spain',
          'coordinate': {'latitude': 40.4168, 'longitude': -3.7038},
        },
      _ => throw StateError('Unexpected request: ${options.path}'),
    };
    return ResponseBody.fromString(
      jsonEncode(body),
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

  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('live search keeps provider credentials behind the backend', () async {
    final adapter = _LocationAdapter();
    final repository =
        LocationRepository(_client(adapter, _liveConfig), _liveConfig);

    final suggestions = await repository.autocomplete(
      query: 'Madrid',
      sessionToken: 'session_123',
      languageCode: 'es',
      regionCode: 'ES',
      biasLatitude: 40.4,
      biasLongitude: -3.7,
    );
    final place = await repository.resolve(
      providerReference: suggestions.single.providerReference,
      sessionToken: 'session_123',
      languageCode: 'es',
    );

    expect(place.formattedAddress, 'Madrid, Spain');
    expect(place.latitude, 40.4168);
    expect(adapter.requests.map((item) => item.path), [
      '/location/places:autocomplete',
      '/location/places:resolve',
    ]);
    expect(adapter.requests.first.data['session_token'], 'session_123');
    expect(adapter.requests.last.data['session_token'], 'session_123');
    expect(adapter.requests.first.data['region_code'], 'ES');
    expect(adapter.requests.first.data['bias'], {
      'latitude': 40.4,
      'longitude': -3.7,
    });
    expect(
      adapter.requests.expand((item) => item.headers.keys),
      isNot(contains('X-Goog-Api-Key')),
    );
  });

  test('demo search is deterministic and does not call the network', () async {
    final adapter = _LocationAdapter();
    final repository =
        LocationRepository(_client(adapter, _demoConfig), _demoConfig);

    final suggestions = await repository.autocomplete(
      query: 'luan',
      sessionToken: 'session_123',
      languageCode: 'pt',
    );
    final place = await repository.resolve(
      providerReference: suggestions.single.providerReference,
      sessionToken: 'session_123',
      languageCode: 'pt',
    );

    expect(place.displayName, 'Luanda');
    expect(place.latitude, -8.838333);
    expect(adapter.requests, isEmpty);
  });
}

ApiClient _client(HttpClientAdapter adapter, AppConfig config) {
  final dio = Dio()..httpClientAdapter = adapter;
  return ApiClient(
    config: config,
    tokenStore: SecureTokenStore(const FlutterSecureStorage()),
    dio: dio,
  );
}

const _liveConfig = AppConfig(
  flavor: AppFlavor.dev,
  apiBaseUrl: 'https://api.example.test',
  demoMode: false,
  connectTimeout: Duration(seconds: 1),
  receiveTimeout: Duration(seconds: 1),
  mapProvider: 'openstreetmap',
  paymentProvider: 'mock',
  pushProvider: 'mock',
  enableBiometricUnlock: false,
);

const _demoConfig = AppConfig(
  flavor: AppFlavor.dev,
  apiBaseUrl: 'https://api.example.test',
  demoMode: true,
  connectTimeout: Duration(seconds: 1),
  receiveTimeout: Duration(seconds: 1),
  mapProvider: 'openstreetmap',
  paymentProvider: 'mock',
  pushProvider: 'mock',
  enableBiometricUnlock: false,
);
