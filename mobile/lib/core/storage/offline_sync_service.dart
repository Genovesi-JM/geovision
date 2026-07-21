import '../config/app_config.dart';
import '../networking/api_client.dart';
import 'offline_queue.dart';

class SyncResult {
  const SyncResult({
    required this.synced,
    required this.failed,
    required this.remaining,
  });

  final int synced;
  final int failed;
  final int remaining;
}

/// Replays durable offline actions in FIFO order. An action is removed only
/// after the backend confirms it; failures stay queued for a future retry.
class OfflineSyncService {
  OfflineSyncService(this._queue, this._api, this._config);

  final OfflineQueue _queue;
  final ApiClient _api;
  final AppConfig _config;
  bool _syncing = false;

  Future<SyncResult> syncNow() async {
    if (_syncing || _config.demoMode) {
      return SyncResult(
        synced: 0,
        failed: 0,
        remaining: _queue.pendingCount,
      );
    }

    _syncing = true;
    var synced = 0;
    var failed = 0;
    try {
      final actions = _queue.readAll();
      for (final action in actions) {
        try {
          switch (action.type) {
            case 'service_request':
              await _api.raw.post(
                '/mobile/service-requests',
                data: action.payload,
              );
              break;
            default:
              await _queue.markAttempt(action.id);
              failed++;
              continue;
          }
          await _queue.remove(action.id);
          synced++;
        } catch (_) {
          await _queue.markAttempt(action.id);
          failed++;
        }
      }
    } finally {
      _syncing = false;
    }

    return SyncResult(
      synced: synced,
      failed: failed,
      remaining: _queue.pendingCount,
    );
  }
}
