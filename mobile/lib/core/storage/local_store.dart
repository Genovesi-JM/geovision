import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// Lightweight JSON cache used by the offline-first repository layer.
///
/// Deliberately dependency-light (shared_preferences, no codegen) so the
/// project builds and tests cleanly without build_runner. Each cached entry
/// stores its payload plus the timestamp it was synchronised, so the UI can
/// always show an honest "last updated" marker and never pretend offline data
/// is live.
class LocalStore {
  LocalStore(this._prefs);
  final SharedPreferences _prefs;

  static Future<LocalStore> create() async =>
      LocalStore(await SharedPreferences.getInstance());

  String _key(String namespace) => 'gv_cache::$namespace';

  Future<void> writeJson(String namespace, Object json) async {
    final envelope = {
      'syncedAt': DateTime.now().toUtc().toIso8601String(),
      'data': json,
    };
    await _prefs.setString(_key(namespace), jsonEncode(envelope));
  }

  CachedEnvelope? readJson(String namespace) {
    final raw = _prefs.getString(_key(namespace));
    if (raw == null) return null;
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      return CachedEnvelope(
        syncedAt: DateTime.tryParse(map['syncedAt'] as String? ?? ''),
        data: map['data'],
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> remove(String namespace) => _prefs.remove(_key(namespace));

  Future<void> clearAll() async {
    final keys = _prefs.getKeys().where((k) => k.startsWith('gv_cache::'));
    for (final k in keys) {
      await _prefs.remove(k);
    }
  }
}

class CachedEnvelope {
  const CachedEnvelope({required this.syncedAt, required this.data});
  final DateTime? syncedAt;
  final dynamic data;
}
