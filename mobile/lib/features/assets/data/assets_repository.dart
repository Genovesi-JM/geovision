import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/networking/connectivity_service.dart';
import '../../../core/networking/data_envelope.dart';
import '../../../core/storage/local_store.dart';
import '../../account/data/customer_experience_repository.dart';
import '../domain/customer_asset.dart';

class AssetsRepository {
  const AssetsRepository(
    this._api,
    this._store,
    this._connectivity,
    this._config,
  );

  final ApiClient _api;
  final LocalStore _store;
  final ConnectivityService _connectivity;
  final AppConfig _config;

  String get _cacheKey => 'canonical_assets::${_api.workspaceId ?? 'default'}';

  Future<DataEnvelope<List<CustomerAsset>>> list() async {
    if (_config.demoMode) {
      final assets = _demoAssets(_api.workspaceId);
      await _store.writeJson(
        _cacheKey,
        assets.map((asset) => asset.toJson()).toList(),
      );
      return DataEnvelope(
        value: assets,
        syncedAt: DateTime.now(),
        fromCache: false,
      );
    }
    if (await _connectivity.isOnline) {
      try {
        final response = await _api.raw.get('/assets');
        final assets = (response.data as List? ?? const [])
            .whereType<Map>()
            .map(
                (row) => CustomerAsset.fromJson(Map<String, dynamic>.from(row)))
            .where((asset) => asset.id.isNotEmpty)
            .toList();
        await _store.writeJson(
          _cacheKey,
          assets.map((asset) => asset.toJson()).toList(),
        );
        return DataEnvelope(
          value: assets,
          syncedAt: DateTime.now(),
          fromCache: false,
        );
      } catch (_) {
        return _cached();
      }
    }
    return _cached();
  }

  Future<CustomerAsset?> detail(String id) async {
    if (_config.demoMode) {
      return _find(_demoAssets(_api.workspaceId), id);
    }
    if (await _connectivity.isOnline) {
      try {
        final response = await _api.raw.get('/assets/$id');
        return CustomerAsset.fromJson(
          Map<String, dynamic>.from(response.data as Map),
        );
      } catch (_) {
        // A cached exact match is safe; never substitute a different asset.
      }
    }
    return _find(_cached().value, id);
  }

  DataEnvelope<List<CustomerAsset>> _cached() {
    final cached = _store.readJson(_cacheKey);
    if (cached?.data is! List) {
      return const DataEnvelope(value: [], syncedAt: null, fromCache: true);
    }
    final assets = (cached!.data as List)
        .whereType<Map>()
        .map((row) => CustomerAsset.fromJson(Map<String, dynamic>.from(row)))
        .where((asset) => asset.id.isNotEmpty)
        .toList();
    return DataEnvelope(
      value: assets,
      syncedAt: cached.syncedAt,
      fromCache: true,
    );
  }

  CustomerAsset? _find(List<CustomerAsset> assets, String id) {
    for (final asset in assets) {
      if (asset.id == id) return asset;
    }
    return null;
  }

  List<CustomerAsset> _demoAssets(String? workspaceId) =>
      workspaceId == 'demo-workspace-infrastructure'
          ? const [
              CustomerAsset(
                id: 'site-3',
                name: 'Madrid M-30 — Tramo 4',
                sector: 'INFRASTRUCTURE',
                assetType: 'ROAD',
                status: 'active',
                locationLabel: 'Madrid, España',
                description:
                    'Seguimiento del avance de obra y de la seguridad vial.',
                metadata: {'length_km': 18.4},
                childrenCount: 2,
                latitude: 40.4168,
                longitude: -3.7038,
              ),
              CustomerAsset(
                id: 'bridge-demo-1',
                name: 'Puente de Toledo',
                sector: 'INFRASTRUCTURE',
                assetType: 'BRIDGE',
                status: 'active',
                locationLabel: 'Madrid, España',
                description: 'Inspección estructural e historial de obra.',
                metadata: {'inspection_cycle_days': 30},
                childrenCount: 0,
                latitude: 40.3983,
                longitude: -3.7141,
              ),
            ]
          : const [
              CustomerAsset(
                id: 'site-1',
                name: 'Finca Madrid Norte',
                sector: 'AGRICULTURE',
                assetType: 'FARM',
                status: 'active',
                locationLabel: 'Comunidad de Madrid, España',
                description: 'Salud del cultivo, riego y operaciones de campo.',
                metadata: {'area_hectares': 1250},
                childrenCount: 4,
                latitude: 40.55,
                longitude: -3.65,
              ),
              CustomerAsset(
                id: 'site-2',
                name: 'Reserva del Humedal de Doñana',
                sector: 'ENVIRONMENTAL',
                assetType: 'ENVIRONMENTAL_SITE',
                status: 'active',
                locationLabel: 'Andalucía, España',
                description: 'Seguimiento del hábitat y del estado del agua.',
                metadata: {'protected': true},
                childrenCount: 1,
                latitude: 37.03,
                longitude: -6.43,
              ),
              CustomerAsset(
                id: 'mine-demo-1',
                name: 'Acopio Minero A',
                sector: 'MINING',
                assetType: 'STOCKPILE',
                status: 'inactive',
                locationLabel: 'Asturias, España',
                description: 'Mediciones de volumen e historial de materiales.',
                metadata: {'material': 'ore'},
                childrenCount: 0,
                latitude: 43.25,
                longitude: -5.78,
              ),
            ];
}

final assetsRepositoryProvider =
    Provider<AssetsRepository>((ref) => AssetsRepository(
          ref.watch(apiClientProvider),
          ref.watch(localStoreProvider),
          ref.watch(connectivityServiceProvider),
          ref.watch(appConfigProvider),
        ));

final customerAssetsProvider =
    FutureProvider<DataEnvelope<List<CustomerAsset>>>((ref) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(assetsRepositoryProvider).list();
});

final customerAssetDetailProvider =
    FutureProvider.family<CustomerAsset?, String>((ref, id) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(assetsRepositoryProvider).detail(id);
});
