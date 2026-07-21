import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/networking/connectivity_service.dart';
import '../../../core/networking/data_envelope.dart';
import '../../../core/storage/local_store.dart';
import '../domain/site.dart';

/// Offline-first sites repository. Strategy: when online + not demo, fetch from
/// the backend and refresh the cache; when offline, serve the last cached copy
/// (never pretending it is live). In demo mode, serve DemoData deterministically.
class SitesRepository {
  SitesRepository(this._api, this._store, this._connectivity, this._config);
  final ApiClient _api;
  final LocalStore _store;
  final ConnectivityService _connectivity;
  final AppConfig _config;

  static const _ns = 'sites';

  Future<DataEnvelope<List<Site>>> getSites() async {
    if (_config.demoMode) {
      final sites = DemoData.sites();
      await _store.writeJson(_ns, sites.map((e) => e.toJson()).toList());
      return DataEnvelope(
          value: sites, syncedAt: DateTime.now(), fromCache: false);
    }

    final online = await _connectivity.isOnline;
    if (online) {
      try {
        final res = await _api.raw.get('/sites');
        final list = (res.data as List)
            .map((e) => Site.fromJson((e as Map).cast<String, dynamic>()))
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

  DataEnvelope<List<Site>> _fromCache() {
    final cached = _store.readJson(_ns);
    if (cached == null) {
      return const DataEnvelope(value: [], syncedAt: null, fromCache: true);
    }
    final list = (cached.data as List)
        .map((e) => Site.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
    return DataEnvelope(
        value: list, syncedAt: cached.syncedAt, fromCache: true);
  }

  Future<Site?> getSite(String id) async {
    final env = await getSites();
    for (final s in env.value) {
      if (s.id == id) return s;
    }
    return null;
  }
}

final sitesRepositoryProvider =
    Provider<SitesRepository>((ref) => SitesRepository(
          ref.watch(apiClientProvider),
          ref.watch(localStoreProvider),
          ref.watch(connectivityServiceProvider),
          ref.watch(appConfigProvider),
        ));

final sitesProvider = FutureProvider<DataEnvelope<List<Site>>>(
    (ref) => ref.watch(sitesRepositoryProvider).getSites());

final siteDetailProvider = FutureProvider.family<Site?, String>(
    (ref, id) => ref.watch(sitesRepositoryProvider).getSite(id));

/// Currently selected site (defaults to the first).
final selectedSiteIdProvider = StateProvider<String?>((ref) => null);
