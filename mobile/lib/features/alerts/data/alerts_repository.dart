import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/networking/connectivity_service.dart';
import '../../../core/networking/data_envelope.dart';
import '../../../core/storage/local_store.dart';
import '../domain/alert.dart';

class AlertsRepository {
  AlertsRepository(this._api, this._store, this._connectivity, this._config);
  final ApiClient _api;
  final LocalStore _store;
  final ConnectivityService _connectivity;
  final AppConfig _config;
  static const _ns = 'alerts';

  final _localState = <String, GvAlert>{};

  Future<DataEnvelope<List<GvAlert>>> getAlerts() async {
    if (_config.demoMode) {
      final list =
          DemoData.alerts().map((a) => _localState[a.id] ?? a).toList();
      await _store.writeJson(_ns, list.map((e) => e.toJson()).toList());
      return DataEnvelope(
          value: list, syncedAt: DateTime.now(), fromCache: false);
    }
    if (await _connectivity.isOnline) {
      try {
        final res = await _api.raw.get('/kpi/alerts');
        final raw = (res.data['alerts'] as List);
        final list = raw
            .map((e) => GvAlert.fromJson((e as Map).cast<String, dynamic>()))
            .toList();
        await _store.writeJson(_ns, list.map((e) => e.toJson()).toList());
        return DataEnvelope(
            value: list, syncedAt: DateTime.now(), fromCache: false);
      } catch (_) {
        return _fromCache();
      }
    }
    return _fromCache();
  }

  DataEnvelope<List<GvAlert>> _fromCache() {
    final cached = _store.readJson(_ns);
    if (cached == null) {
      return const DataEnvelope(value: [], syncedAt: null, fromCache: true);
    }
    final list = (cached.data as List)
        .map((e) => GvAlert.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
    return DataEnvelope(
        value: list, syncedAt: cached.syncedAt, fromCache: true);
  }

  /// Optimistic local acknowledge; backend call is best-effort in real mode.
  Future<void> acknowledge(String id) async {
    final env = await getAlerts();
    final a = env.value.firstWhere((e) => e.id == id);
    _localState[id] = a.copyWith(acknowledged: true);
    if (!_config.demoMode) {
      try {
        await _api.raw.post('/kpi/alerts/$id/acknowledge');
      } catch (_) {/* queued/best-effort */}
    }
  }
}

final alertsRepositoryProvider =
    Provider<AlertsRepository>((ref) => AlertsRepository(
          ref.watch(apiClientProvider),
          ref.watch(localStoreProvider),
          ref.watch(connectivityServiceProvider),
          ref.watch(appConfigProvider),
        ));

final alertsProvider = FutureProvider<DataEnvelope<List<GvAlert>>>(
    (ref) => ref.watch(alertsRepositoryProvider).getAlerts());
