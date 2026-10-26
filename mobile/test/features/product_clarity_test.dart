import 'package:geovision/features/devices/presentation/device_control_screen.dart';
import 'package:geovision/features/devices/data/devices_repository.dart';
import 'package:geovision/integrations/iot/mock_iot_provider.dart';
import 'dart:convert';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/localization/journey_copy.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/networking/connectivity_service.dart';
import 'package:geovision/core/storage/local_store.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/features/account/data/customer_experience_repository.dart';
import 'package:geovision/features/account/domain/customer_experience.dart';
import 'package:geovision/features/assistant/data/gaia_repository.dart';
import 'package:geovision/features/devices/domain/device.dart';
import 'package:geovision/features/orders/domain/product.dart';
import 'package:geovision/features/orders/domain/currency.dart';
import 'package:geovision/features/orders/domain/quantity_plan.dart';
import 'package:geovision/integrations/iot/backend_iot_provider.dart';
import 'package:geovision/integrations/iot/iot_provider.dart';
import '../core/live_provider_selection_test.dart' show config;

class _Online extends ConnectivityService {
  @override
  Future<bool> get isOnline async => true;
}

class _Experience extends CustomerExperienceController {
  @override
  Future<CustomerExperience> build() async => const CustomerExperience(
      activeWorkspaceId: 'w',
      activeOrganizationId: 'org',
      permissions: {},
      capabilities: {},
      workspaces: []);
}

class _OperatorExperience extends CustomerExperienceController {
  @override Future<CustomerExperience> build() async => const CustomerExperience(activeWorkspaceId: 'w', activeOrganizationId: 'org', permissions: {'workspace:operate'}, capabilities: {}, workspaces: []);
}
class _CommandRepository extends DevicesRepository {
  _CommandRepository() : super(const MockIotProvider());
  final sent = <DeviceCommand>[];
  @override Future<IotOperationResult> sendCommand(DeviceCommand command) async {
    sent.add(command);
    return const IotOperationResult(IotOutcome.pending, data: {'command_id': 'pending-one'});
  }
}
class _Adapter implements HttpClientAdapter {
  int status = 202;
  Object body = {
    'outcome': 'pending',
    'data': {'command_id': 'command-1'}
  };
  RequestOptions? last;
  bool gaia = false;
  final paths = <String>[];
  Map<String, dynamic>? chat;
  @override
  Future<ResponseBody> fetch(
      RequestOptions o, Stream<Uint8List>? stream, Future<void>? cancel) async {
    last = o;
    paths.add(o.path);
    var result = body;
    var code = status;
    if (gaia) {
      code = 200;
      if (o.path == '/assets') {
        result = [
          {
            'id': 'asset-a',
            'name': 'Asset A',
            'sector': 'AGRO',
            'asset_type': 'FARM',
            'status': 'active'
          },
          {
            'id': 'asset-b',
            'name': 'Asset B',
            'sector': 'MINING',
            'asset_type': 'MINE',
            'status': 'active'
          }
        ];
      } else if (o.path == '/mobile/devices') {
        result = {
          'items': [
            {
              'id': 'pump-a',
              'name': 'Pump A',
              'core_asset_id': 'asset-a',
              'status': 'online'
            },
            {
              'id': 'pump-b',
              'name': 'Pump B',
              'core_asset_id': 'asset-b',
              'status': 'offline'
            }
          ]
        };
      } else if (o.path == '/ai/chat') {
        chat = Map<String, dynamic>.from(o.data as Map);
        result = {'reply': 'Test response'};
      } else {
        code = 503;
        result = {'detail': 'optional source unavailable'};
      }
    }
    return ResponseBody.fromString(jsonEncode(result), code, headers: {
      Headers.contentTypeHeader: [Headers.jsonContentType]
    });
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _Adapter adapter;
  late ApiClient api;
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    SharedPreferences.setMockInitialValues({});
    adapter = _Adapter();
    api = ApiClient(
        config: config(false),
        tokenStore: SecureTokenStore(),
        dio: Dio()..httpClientAdapter = adapter)
      ..selectWorkspace('w');
  });
  for (final operator in [false, true]) {
    testWidgets('control screen ${operator ? 'confirms and locks a pending command' : 'blocks a viewer'}', (tester) async {
      final repo = _CommandRepository();
      await tester.pumpWidget(ProviderScope(overrides: [
        customerExperienceProvider.overrideWith(operator ? _OperatorExperience.new : _Experience.new),
        devicesRepositoryProvider.overrideWithValue(repo),
        deviceControlProvider('d').overrideWith((ref) async => {'name': 'Test pump', 'site_name': 'Site A', 'allow_remote_control': true, 'capabilities': ['command:relay_on'], 'commands': <Map<String, dynamic>>[]}),
      ], child: const MaterialApp(home: DeviceControlScreen(deviceId: 'd'))));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), 'Supervised valve test');
      await tester.pump();
      final button = find.widgetWithText(OutlinedButton, 'Turn output on');
      expect(tester.widget<OutlinedButton>(button).onPressed != null, operator);
      if (!operator) { expect(repo.sent, isEmpty); return; }
      await tester.ensureVisible(button); await tester.tap(button); await tester.pumpAndSettle();
      expect(repo.sent, isEmpty);
      await tester.tap(find.text('Confirm send')); await tester.pumpAndSettle();
      expect(repo.sent, hasLength(1)); expect(repo.sent.single.reason, 'Supervised valve test');
      expect(find.text('Request received. Await device confirmation.'), findsOneWidget);
      expect(tester.widget<OutlinedButton>(button).onPressed, isNull,
          reason: 'A lagging empty history must not permit another command.');
    });
  }
  test('missing and invalid telemetry is unknown, while zero remains zero', () {
    final missing = GvDevice.fromJson({'id': 'd'});
    expect(missing.batteryPercent, isNull);
    expect(missing.signalPercent, isNull);
    expect(missing.status, 'unknown');
    final zero = GvDevice.fromJson(
        {'id': 'd', 'battery_percent': 0, 'signal_percent': 150});
    expect(zero.batteryPercent, 0);
    expect(zero.signalPercent, isNull);
  });
  test('missing catalogue data cannot imply a purchasable free in-stock item',
      () {
    final p = GvProduct.fromJson({'id': 'p', 'product_type': 'hardware'});
    expect(p.requiresEnquiry, isTrue);
    expect(p.stockStatus, 'unknown');
    expect(StoreMoney.productCents(p, StoreCurrency.usd), isNull);
  });
  test('prices retain source currency and never silently use demo FX', () {
    final p = GvProduct.fromJson({
      'id': 'p',
      'price_cents': 12000,
      'currency': 'EUR',
      'price_model': 'FIXED',
      'stock_status': 'in_stock',
      'product_type': 'hardware'
    });
    expect(StoreMoney.productCents(p, StoreCurrency.eur), 12000);
    expect(StoreMoney.productCents(p, StoreCurrency.usd), isNull);
    expect(StoreMoney.productCents(p, StoreCurrency.akz), isNull);
    expect(
        StoreMoney.formatProduct(p, StoreCurrency.usd,
            unavailable: 'Consultar'),
        'Consultar');
  });
  test('legacy explicit USD/EUR/AOA price lists retain their actual units', () {
    final p = GvProduct.fromJson({
      'id': 'p',
      'price_usd': 10000,
      'price_eur': 9500,
      'price': 9000000,
      'currency': 'AOA'
    });
    expect(StoreMoney.productCents(p, StoreCurrency.usd), 10000);
    expect(StoreMoney.productCents(p, StoreCurrency.eur), 9500);
    expect(StoreMoney.productCents(p, StoreCurrency.akz), 9000000);
  });
  test('sufficient stock recommends zero, otherwise only complete packs', () {
    expect(QuantityPlan(need: 100, usableStock: 120, packSize: 50).packs, 0);
    final p = QuantityPlan(need: 120, usableStock: 30, packSize: 50);
    expect(p.packs, 2);
    expect(p.shortfall, 90);
    expect(p.surplus, 10);
    expect(QuantityPlan(need: 0.14, usableStock: 0, packSize: 0.01).packs, 14);
    expect(() => QuantityPlan(need: -1, usableStock: 0, packSize: 5),
        throwsArgumentError);
    expect(() => QuantityPlan(need: 10, usableStock: 0, packSize: 0),
        throwsArgumentError);
  });
  test(
      'command contract includes reason and does not equate queued with completed',
      () async {
    final result = await BackendIotProvider(api).sendCommand(
        const DeviceCommand(
            deviceId: 'd',
            name: 'relay_on',
            reason: 'Supervised test',
            arguments: {'confirmed': true}));
    expect(adapter.last!.data, {
      'name': 'relay_on',
      'arguments': {},
      'confirmed': true,
      'reason': 'Supervised test'
    });
    expect(result.outcome, IotOutcome.pending);
    expect(result.succeeded, isFalse);
    expect(result.data['command_id'], 'command-1');
  });
  test('malformed success responses fail closed', () async {
    adapter.status = 200;
    adapter.body = {};
    expect((await BackendIotProvider(api).diagnose('d')).succeeded, isFalse);
  });
  for (final entry in {
    403: IotOutcome.permissionRequired,
    404: IotOutcome.notFound,
    409: IotOutcome.rejected,
    422: IotOutcome.invalidInput
  }.entries) {
    test('HTTP ${entry.key} retains its distinct meaning', () async {
      adapter.status = entry.key;
      adapter.body = {'detail': 'test'};
      expect(
          (await BackendIotProvider(api).sendCommand(
                  const DeviceCommand(deviceId: 'd', name: 'relay_on')))
              .outcome,
          entry.value);
    });
  }
  test('missing reading timestamp remains unknown', () async {
    adapter.status = 200;
    adapter.body = {'label': 'No sample', 'at': null};
    expect((await BackendIotProvider(api).subscribeReadings('d').first).at,
        isNull);
  });
  for (final device in <String?>[null, 'pump-b']) {
    test(
        'GAIA context ${device ?? 'unselected'} avoids unrelated assets and tolerates unavailable optional data',
        () async {
      adapter.gaia = true;
      final container = ProviderContainer(overrides: [
        appConfigProvider.overrideWithValue(config(false)),
        apiClientProvider.overrideWithValue(api),
        localStoreProvider.overrideWithValue(
            LocalStore(await SharedPreferences.getInstance())),
        connectivityServiceProvider.overrideWithValue(_Online()),
        customerExperienceProvider.overrideWith(_Experience.new)
      ]);
      addTearDown(container.dispose);
      final reply = await container.read(gaiaRepositoryProvider).send(
          const [GaiaMessage(role: 'user', content: 'Explain this device')],
          deviceId: device, productId: 'unavailable');
      expect(reply, 'Test response');
      final context = adapter.chat!['page_text'] as String;
      expect(context, contains('Unavailable context source: catalogue'));
      expect(context, isNot(contains('Device: pump-a')));
      if (device == null) {
        expect(context, contains('No verified asset selected'));
        expect(context, isNot(contains('Selected asset: asset-a')));
      } else {
        expect(context, contains('Selected asset: asset-b'));
        expect(context, contains('Device: pump-b'));
        expect(context, contains('battery unknown'));
      }
    });
  }
  for (final locale in ['pt', 'es', 'en']) {
    testWidgets('journey helper selects $locale', (tester) async {
      String? value;
      await tester.pumpWidget(Localizations(
          locale: Locale(locale),
          delegates: const [DefaultWidgetsLocalizations.delegate],
          child: Builder(builder: (context) {
            value = journeyText(context, 'Tienda', 'Shop', pt: 'Loja');
            return const SizedBox();
          })));
      expect(value, {'pt': 'Loja', 'es': 'Tienda', 'en': 'Shop'}[locale]);
    });
  }
}
