import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/networking/connectivity_service.dart';
import '../../../core/storage/offline_queue.dart';
import '../../account/data/customer_experience_repository.dart';
import '../domain/service_request.dart';

/// Work / service requests. New requests are enqueued durably; if offline they
/// stay in the pending queue and surface with a "pending sync" badge — no
/// silent loss of customer data.
class WorkRepository {
  WorkRepository(this._api, this._queue, this._connectivity, this._config);
  final ApiClient _api;
  final OfflineQueue _queue;
  final ConnectivityService _connectivity;
  final AppConfig _config;

  final _local = <String, List<ServiceRequest>>{};

  String get _workspaceKey => _api.workspaceId ?? 'default';
  List<ServiceRequest> get _currentLocal =>
      _local.putIfAbsent(_workspaceKey, () => []);

  List<ServiceRequest> _pendingFromQueue() {
    final workspaceId = _api.workspaceId;
    return _queue
        .readAll()
        .where((action) {
          if (action.type != 'service_request') return false;
          final queuedWorkspace = action.payload['workspace_id']?.toString();
          // Legacy unscoped entries cannot safely be attributed once a
          // workspace is selected, so keep them queued but do not display
          // them under an arbitrary customer workspace.
          if (workspaceId == null) return queuedWorkspace == null;
          return queuedWorkspace == workspaceId;
        })
        .map((action) => ServiceRequest.fromJson({
              ...action.payload,
              'pending_sync': true,
            }))
        .toList();
  }

  Future<List<ServiceRequest>> getRequests() async {
    final base =
        _config.demoMode ? DemoData.serviceRequests() : <ServiceRequest>[];
    if (!_config.demoMode && await _connectivity.isOnline) {
      try {
        final res = await _api.raw.get('/mobile/service-requests');
        final list = (res.data as List)
            .map((e) =>
                ServiceRequest.fromJson((e as Map).cast<String, dynamic>()))
            .toList();
        return [..._pendingFromQueue(), ...list];
      } catch (_) {/* fall through to local */}
    }
    return [..._pendingFromQueue(), ..._currentLocal, ...base];
  }

  Future<ServiceRequest?> getRequest(String id) async {
    if (_config.demoMode) {
      final items = [..._currentLocal, ...DemoData.serviceRequests()];
      for (final item in items) {
        if (item.id == id) return item;
      }
      return null;
    }
    final pending = _pendingFromQueue();
    for (final item in pending) {
      if (item.id == id) return item;
    }
    final response = await _api.raw.get('/mobile/service-requests/$id');
    return ServiceRequest.fromJson(
        Map<String, dynamic>.from(response.data as Map));
  }

  Future<ServiceRequest> submit({
    required ServiceType type,
    required String siteId,
    required String siteName,
    required String urgency,
    required String description,
    List<String> attachments = const [],
  }) async {
    final payload = {
      'id': DateTime.now().microsecondsSinceEpoch.toString(),
      'type': type.name,
      'site_id': siteId,
      'site_name': siteName,
      'urgency': urgency,
      'description': description,
      'status': 'submitted',
      'created_at': DateTime.now().toUtc().toIso8601String(),
      'attachments': attachments,
      if (_api.workspaceId case final workspaceId?) 'workspace_id': workspaceId,
    };

    final online = await _connectivity.isOnline;
    if (!_config.demoMode && online) {
      try {
        final res =
            await _api.raw.post('/mobile/service-requests', data: payload);
        return ServiceRequest.fromJson(
            (res.data as Map).cast<String, dynamic>());
      } catch (_) {
        await _queue.enqueue('service_request', payload);
        return ServiceRequest.fromJson({...payload, 'pending_sync': true});
      }
    }
    // Demo or offline: persist locally / enqueue.
    if (_config.demoMode) {
      final req = ServiceRequest.fromJson(payload);
      _currentLocal.insert(0, req);
      return req;
    }
    await _queue.enqueue('service_request', payload);
    return ServiceRequest.fromJson({...payload, 'pending_sync': true});
  }

  int get pendingCount => _queue.pendingCount;
}

final workRepositoryProvider = Provider<WorkRepository>((ref) => WorkRepository(
      ref.watch(apiClientProvider),
      ref.watch(offlineQueueProvider),
      ref.watch(connectivityServiceProvider),
      ref.watch(appConfigProvider),
    ));

final serviceRequestsProvider =
    FutureProvider<List<ServiceRequest>>((ref) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(workRepositoryProvider).getRequests();
});

final serviceRequestDetailProvider =
    FutureProvider.family<ServiceRequest?, String>((ref, id) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(workRepositoryProvider).getRequest(id);
});
