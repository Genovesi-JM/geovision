import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/networking/api_client.dart';
import '../../account/data/customer_experience_repository.dart';
import '../domain/customer_action.dart';

class ActionsRepository {
  const ActionsRepository(this._api, this._config);
  final ApiClient _api;
  final AppConfig _config;

  static final _demo = [
    CustomerAction(
      id: 'action-demo-critical',
      assetId: 'site-1',
      title: 'Inspect the Block A irrigation pump',
      description:
          'Soil moisture fell rapidly. Confirm the valve and pump condition before the next irrigation cycle.',
      priority: 'CRITICAL',
      status: 'OPEN',
      lifecycleVersion: 1,
      createdAt: DateTime(2026, 9, 10, 8),
    ),
    CustomerAction(
      id: 'action-demo-attention',
      assetId: 'site-3',
      title: 'Replace collar A17 battery',
      description: 'Battery is below the operating threshold.',
      priority: 'HIGH',
      status: 'IN_PROGRESS',
      lifecycleVersion: 2,
      createdAt: DateTime(2026, 9, 9, 15),
    ),
    CustomerAction(
      id: 'action-demo-scheduled',
      assetId: 'site-1',
      title: 'Review field inspection',
      description: 'GeoVision Field Team inspection is scheduled.',
      priority: 'MEDIUM',
      status: 'OPEN',
      lifecycleVersion: 1,
      createdAt: DateTime(2026, 9, 10, 9),
      dueDate: DateTime(2099, 9, 11, 9),
    ),
    CustomerAction(
      id: 'action-demo-completed',
      assetId: 'site-2',
      title: 'Validate the latest NDVI result',
      description: 'The result was reviewed and accepted.',
      priority: 'MEDIUM',
      status: 'COMPLETED',
      lifecycleVersion: 3,
      createdAt: DateTime(2026, 9, 2, 10),
      completedAt: DateTime(2026, 9, 9, 10),
    ),
  ];

  Future<CustomerActionBuckets> load({String? assetId}) async {
    if (_config.demoMode) {
      return CustomerActionBuckets.fromItems(assetId == null
          ? _demo
          : _demo.where((item) => item.assetId == assetId).toList());
    }
    final response = await _api.raw.get('/mobile/actions');
    final buckets = CustomerActionBuckets.fromJson(response.data);
    if (assetId == null) return buckets;
    // Filtering the tenant-scoped projection locally keeps per-asset
    // navigation compatible even while older deployments ignore asset_id.
    return CustomerActionBuckets.fromItems(
      buckets.all.where((item) => item.assetId == assetId).toList(),
    );
  }

  Future<CustomerAction?> detail(String actionId) async {
    if (_config.demoMode) {
      for (final item in _demo) {
        if (item.id == actionId) return item;
      }
      return null;
    }
    final response = await _api.raw.get('/actions/$actionId');
    return CustomerAction.fromJson(
        Map<String, dynamic>.from(response.data as Map));
  }
}

final actionsRepositoryProvider = Provider<ActionsRepository>((ref) =>
    ActionsRepository(
        ref.watch(apiClientProvider), ref.watch(appConfigProvider)));

final actionsProvider =
    FutureProvider.family<CustomerActionBuckets, String?>((ref, assetId) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(actionsRepositoryProvider).load(assetId: assetId);
});

final actionDetailProvider =
    FutureProvider.family<CustomerAction?, String>((ref, actionId) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(actionsRepositoryProvider).detail(actionId);
});
