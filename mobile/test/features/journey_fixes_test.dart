import 'dart:convert';
import 'package:geovision/features/account/data/customer_experience_repository.dart';
import 'package:geovision/features/account/domain/customer_experience.dart';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/networking/api_client.dart';
import 'package:geovision/core/networking/connectivity_service.dart';
import 'package:geovision/core/networking/data_envelope.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:geovision/core/storage/offline_queue.dart';
import 'package:geovision/features/assets/data/assets_repository.dart';
import 'package:geovision/features/assets/domain/customer_asset.dart';
import 'package:geovision/features/orders/data/payment_availability.dart';
import 'package:geovision/features/orders/domain/product.dart';
import 'package:geovision/features/reports/data/reports_repository.dart';
import 'package:geovision/features/reports/data/report_files.dart';
import 'package:geovision/features/reports/presentation/report_actions.dart';
import 'package:geovision/features/work/data/work_repository.dart';
import 'package:geovision/features/work/domain/service_request.dart';
import 'package:geovision/features/work/presentation/new_request_screen.dart';
import 'package:geovision/l10n/app_localizations.dart';
import '../core/live_provider_selection_test.dart' show config;

class _Experience extends CustomerExperienceController {
  @override
  Future<CustomerExperience> build() async => const CustomerExperience(
      activeWorkspaceId: 'workspace-a',
      activeOrganizationId: 'org-a',
      permissions: {},
      capabilities: {},
      workspaces: []);
}

class _Online extends ConnectivityService {
  @override
  Future<bool> get isOnline async => true;
}

class _Adapter implements HttpClientAdapter {
  int status = 200;
  String pdf = '%PDF-1.7\nsynthetic test document';
  RequestOptions? request;
  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? stream,
      Future<void>? cancelled) async {
    request = options;
    if (options.path.endsWith('/download')) {
      return ResponseBody.fromString(status == 200 ? pdf : 'Forbidden', status,
          headers: {
            'content-type': ['application/pdf']
          });
    }
    return ResponseBody.fromString(
        jsonEncode({...options.data as Map, 'id': 'server-request'}), status,
        headers: {
          'content-type': ['application/json']
        });
  }

  @override
  void close({bool force = false}) {}
}

class _Files extends ReportFiles {
  final saves = <bool>[];
  @override
  Future<void> present(Uint8List bytes,
      {required bool save, required Rect origin}) async {
    expect(String.fromCharCodes(bytes.take(5)), '%PDF-');
    expect(origin.isEmpty, isFalse);
    saves.add(save);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ApiClient api;
  late _Adapter adapter;
  late SecureTokenStore tokens;
  late OfflineQueue queue;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    FlutterSecureStorage.setMockInitialValues({});
    tokens = SecureTokenStore();
    await tokens.saveTokens(access: 'test-access', refresh: 'test-refresh');
    adapter = _Adapter();
    api = ApiClient(
        config: config(false),
        tokenStore: tokens,
        dio: Dio()..httpClientAdapter = adapter)
      ..selectWorkspace('workspace-a');
    queue = OfflineQueue(await SharedPreferences.getInstance());
  });
  test('PDF carries auth and workspace; rejects forbidden and non-PDF content',
      () async {
    final repo = ReportsRepository(config(false), api);
    expect(await repo.download('report-a'), isNotEmpty);
    expect(adapter.request!.path, '/reports/report-a/download');
    expect(adapter.request!.headers['Authorization'], 'Bearer test-access');
    expect(adapter.request!.headers['X-Workspace-ID'], 'workspace-a');
    expect(adapter.request!.queryParameters, isEmpty);
    adapter.pdf = '<html>not a PDF</html>';
    await expectLater(repo.download('report-a'), throwsFormatException);
    adapter.status = 403;
    await expectLater(repo.download('report-a'), throwsA(isA<DioException>()));
  });
  test('canonical requests preserve asset; rejected requests are not queued',
      () async {
    final repo = WorkRepository(api, queue, _Online(), config(false));
    Future<ServiceRequest> submit() => repo.submit(
        type: ServiceType.inspection,
        siteId: 'canonical-only',
        canonicalAsset: true,
        siteName: 'Field',
        urgency: 'normal',
        description: 'Inspect');
    expect((await submit()).siteId, 'canonical-only');
    expect(adapter.request!.data['asset_id'], 'canonical-only');
    expect((adapter.request!.data as Map).containsKey('site_id'), isFalse);
    expect(adapter.request!.headers['Idempotency-Key'], isNotEmpty);
    adapter.status = 403;
    await expectLater(submit(), throwsA(isA<DioException>()));
    expect(queue.pendingCount, 0);
    adapter.status = 503;
    expect((await submit()).pendingSync, isTrue);
    expect(queue.readAll().single.payload['asset_id'], 'canonical-only');
  });
  test('live mock configuration cannot advertise payments', () async {
    final container = ProviderContainer(
        overrides: [appConfigProvider.overrideWithValue(config(false))]);
    addTearDown(container.dispose);
    expect(await container.read(availablePaymentsProvider.future), isEmpty);
  });
  test('quotes, scheduling and subscriptions require an enquiry', () {
    GvProduct product(Map<String, dynamic> fields) => GvProduct.fromJson({
          'id': 'x',
          'product_type': 'hardware',
          'price_cents': 1000,
          'currency': 'EUR',
          'price_model': 'FIXED',
          'stock_status': 'in_stock',
          ...fields
        });
    expect(product({}).requiresEnquiry, isFalse);
    for (final fields in [
      {'price_model': 'QUOTE'},
      {'requires_site': true},
      {'requires_scheduling': true},
      {'product_type': 'subscription'},
      {'product_type': 'service'}
    ]) {
      expect(product(fields).requiresEnquiry, isTrue);
    }
  });
  testWidgets(
      'report buttons fetch PDF, invoke viewer/save and retry after error',
      (tester) async {
    final files = _Files();
    await tester.pumpWidget(ProviderScope(
        overrides: [
          appConfigProvider.overrideWithValue(config(false)),
          apiClientProvider.overrideWithValue(api),
          secureTokenStoreProvider.overrideWithValue(tokens),
          reportFilesProvider.overrideWithValue(files)
        ],
        child: const MaterialApp(
            home: Scaffold(body: ReportActions(reportId: 'report-a')))));
    await tester.tap(find.text('Open PDF'));
    await tester.pumpAndSettle();
    expect(files.saves, [false]);
    adapter.status = 403;
    await tester.tap(find.text('Save or share PDF'));
    await tester.pumpAndSettle();
    expect(files.saves, [false]);
    expect(find.textContaining('Could not open the PDF'), findsOneWidget);
    adapter.status = 200;
    await tester.tap(find.text('Save or share PDF'));
    await tester.pumpAndSettle();
    expect(files.saves, [false, true]);
  });
  testWidgets(
      'request retains selected asset and never substitutes a missing one',
      (tester) async {
    const asset = CustomerAsset(
        id: 'asset-a',
        name: 'Field A',
        sector: 'AGRICULTURE',
        assetType: 'FARM',
        status: 'active',
        locationLabel: '',
        description: '',
        metadata: {},
        childrenCount: 0);
    Future<void> mount(String selected) async {
      await tester.pumpWidget(ProviderScope(
          overrides: [
            appConfigProvider.overrideWithValue(config(false)),
            apiClientProvider.overrideWithValue(api),
            customerExperienceProvider.overrideWith(_Experience.new),
            customerAssetsProvider.overrideWith((ref) async =>
                const DataEnvelope(
                    value: [asset], fromCache: false, syncedAt: null))
          ],
          child: MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: NewRequestScreen(
                  key: ValueKey(selected), assetId: selected))));
      await tester.pumpAndSettle();
    }

    await mount('asset-a');
    expect(
        tester
            .widget<DropdownButton<String>>(find.byType(DropdownButton<String>))
            .value,
        'asset-a');
    await mount('missing-asset');
    expect(
        tester
            .widget<DropdownButton<String>>(find.byType(DropdownButton<String>))
            .value,
        isNull);
    expect(
        find.textContaining('selected asset is unavailable'), findsOneWidget);
    final attachment = find.widgetWithText(OutlinedButton, 'Attach file');
    await tester.scrollUntilVisible(attachment, 300,
        scrollable: find
            .descendant(
                of: find.byType(ListView), matching: find.byType(Scrollable))
            .first);
    expect(tester.widget<OutlinedButton>(attachment).onPressed, isNull);
  });
}
