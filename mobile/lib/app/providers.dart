import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/config/app_config.dart';
import '../core/networking/api_client.dart';
import '../core/networking/connectivity_service.dart';
import '../core/storage/local_store.dart';
import '../core/storage/offline_queue.dart';
import '../core/storage/secure_token_store.dart';
import '../integrations/iot/iot_provider.dart';
import '../integrations/iot/mock_iot_provider.dart';
import '../integrations/maps/demo_map_provider.dart';
import '../integrations/maps/map_provider.dart';
import '../integrations/maps/mapbox_map_provider.dart';
import '../integrations/payments/bank_transfer_provider.dart';
import '../integrations/payments/mock_payment_provider.dart';
import '../integrations/payments/payment_provider.dart';
import '../integrations/push/mock_push_provider.dart';
import '../integrations/push/push_provider.dart';

/// Root configuration — overridden in main() with the resolved AppConfig.
final appConfigProvider =
    Provider<AppConfig>((ref) => throw UnimplementedError());

/// Injected in main() after async init so widgets can read synchronously.
final sharedPrefsProvider =
    Provider<SharedPreferences>((ref) => throw UnimplementedError());

final secureTokenStoreProvider =
    Provider<SecureTokenStore>((ref) => SecureTokenStore());

final localStoreProvider =
    Provider<LocalStore>((ref) => LocalStore(ref.watch(sharedPrefsProvider)));

final offlineQueueProvider = Provider<OfflineQueue>(
    (ref) => OfflineQueue(ref.watch(sharedPrefsProvider)));

final connectivityServiceProvider =
    Provider<ConnectivityService>((ref) => ConnectivityService());

final connectivityStatusProvider = StreamProvider<bool>((ref) {
  return ref.watch(connectivityServiceProvider).onStatusChange;
});

final apiClientProvider = Provider<ApiClient>((ref) => ApiClient(
      config: ref.watch(appConfigProvider),
      tokenStore: ref.watch(secureTokenStoreProvider),
    ));

// ── Pluggable provider adapters (feature-flag selected) ────────────────────

final mapProviderProvider = Provider<MapProvider>((ref) {
  final cfg = ref.watch(appConfigProvider);
  switch (cfg.mapProvider) {
    case 'mapbox':
      const token = String.fromEnvironment('GV_MAPBOX_TOKEN');
      if (token.isNotEmpty) return const MapboxMapProvider(token);
      return const DemoMapProvider();
    default:
      return const DemoMapProvider();
  }
});

final paymentProviderProvider = Provider<PaymentProvider>((ref) {
  final cfg = ref.watch(appConfigProvider);
  switch (cfg.paymentProvider) {
    case 'bank_transfer':
      return const BankTransferProvider();
    // 'stripe' / 'multicaixa' are gated on credentials — see HUMAN_GATES.md
    default:
      return const MockPaymentProvider();
  }
});

final pushProviderProvider =
    Provider<PushProvider>((ref) => MockPushProvider());

final iotProviderProvider =
    Provider<IotProvider>((ref) => const MockIotProvider());
