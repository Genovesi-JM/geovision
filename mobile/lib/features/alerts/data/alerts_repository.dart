import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/networking/connectivity_service.dart';
import '../../../core/networking/data_envelope.dart';
import '../../../core/storage/local_store.dart';
import '../../account/data/customer_experience_repository.dart';
import '../domain/alert.dart';

class AlertsRepository {
  AlertsRepository(this._api, this._store, this._connectivity, this._config);
  final ApiClient _api;
  final LocalStore _store;
  final ConnectivityService _connectivity;
  final AppConfig _config;
  String get _namespace => 'alerts::${_api.workspaceId ?? 'default'}';

  final _localState = <String, GvAlert>{};

  Future<DataEnvelope<List<GvAlert>>> getAlerts() async {
    if (_config.demoMode) {
      final list =
          DemoData.alerts().map((a) => _localState[a.id] ?? a).toList();
      await _store.writeJson(_namespace, list.map((e) => e.toJson()).toList());
      return DataEnvelope(
          value: list, syncedAt: DateTime.now(), fromCache: false);
    }
    if (await _connectivity.isOnline) {
      try {
        final res = await _api.raw.get('/iot/alerts');
        final raw = res.data as List;
        final list = raw
            .map((e) => GvAlert.fromJson((e as Map).cast<String, dynamic>()))
            .toList();
        await _store.writeJson(
            _namespace, list.map((e) => e.toJson()).toList());
        return DataEnvelope(
            value: list, syncedAt: DateTime.now(), fromCache: false);
      } catch (_) {
        return _fromCache();
      }
    }
    return _fromCache();
  }

  DataEnvelope<List<GvAlert>> _fromCache() {
    final cached = _store.readJson(_namespace);
    if (cached == null) {
      return const DataEnvelope(value: [], syncedAt: null, fromCache: true);
    }
    final list = (cached.data as List)
        .map((e) => GvAlert.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
    return DataEnvelope(
        value: list, syncedAt: cached.syncedAt, fromCache: true);
  }

  /// Acknowledgement records receipt only; it does not resolve the alert.
  Future<void> acknowledge(String id) async {
    if (!_config.demoMode) {
      await _api.raw.post('/iot/alerts/$id/acknowledge');
      return;
    }
    final a = _localState[id] ?? DemoData.alerts().where((a) => a.id == id).firstOrNull;
    if (a != null) _localState[id] = a.copyWith(acknowledged: true);
  }
}

final alertsRepositoryProvider =
    Provider<AlertsRepository>((ref) => AlertsRepository(
          ref.watch(apiClientProvider),
          ref.watch(localStoreProvider),
          ref.watch(connectivityServiceProvider),
          ref.watch(appConfigProvider),
        ));

final alertsProvider = FutureProvider<DataEnvelope<List<GvAlert>>>((ref) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(alertsRepositoryProvider).getAlerts();
});
