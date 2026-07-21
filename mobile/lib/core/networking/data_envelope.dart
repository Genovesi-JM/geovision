/// Wraps repository results with freshness metadata so the UI can always show
/// an honest last-synced marker and whether data came from cache (offline).
class DataEnvelope<T> {
  const DataEnvelope(
      {required this.value, required this.syncedAt, required this.fromCache});
  final T value;
  final DateTime? syncedAt;
  final bool fromCache;
}
