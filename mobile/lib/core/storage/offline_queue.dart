import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// A durable FIFO queue of user actions created while offline (e.g. service
/// requests, evidence uploads). Nothing is ever silently dropped: entries
/// persist until they are explicitly acknowledged as synced.
class OfflineQueue {
  OfflineQueue(this._prefs);
  final SharedPreferences _prefs;
  static const _key = 'gv_offline_queue';

  static Future<OfflineQueue> create() async =>
      OfflineQueue(await SharedPreferences.getInstance());

  List<QueuedAction> readAll() {
    final raw = _prefs.getString(_key);
    if (raw == null) return [];
    final list = (jsonDecode(raw) as List).cast<Map<String, dynamic>>();
    return list.map(QueuedAction.fromJson).toList();
  }

  Future<QueuedAction> enqueue(
      String type, Map<String, dynamic> payload) async {
    final actions = readAll();
    final action = QueuedAction(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      type: type,
      payload: payload,
      createdAt: DateTime.now().toUtc(),
      attempts: 0,
    );
    actions.add(action);
    await _persist(actions);
    return action;
  }

  Future<void> markAttempt(String id) async {
    final actions = readAll();
    final idx = actions.indexWhere((a) => a.id == id);
    if (idx == -1) return;
    actions[idx] = actions[idx].copyWith(attempts: actions[idx].attempts + 1);
    await _persist(actions);
  }

  Future<void> remove(String id) async {
    final actions = readAll()..removeWhere((a) => a.id == id);
    await _persist(actions);
  }

  int get pendingCount => readAll().length;

  Future<void> _persist(List<QueuedAction> actions) => _prefs.setString(
      _key, jsonEncode(actions.map((a) => a.toJson()).toList()));
}

class QueuedAction {
  const QueuedAction({
    required this.id,
    required this.type,
    required this.payload,
    required this.createdAt,
    required this.attempts,
  });

  final String id;
  final String type;
  final Map<String, dynamic> payload;
  final DateTime createdAt;
  final int attempts;

  QueuedAction copyWith({int? attempts}) => QueuedAction(
        id: id,
        type: type,
        payload: payload,
        createdAt: createdAt,
        attempts: attempts ?? this.attempts,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type,
        'payload': payload,
        'createdAt': createdAt.toIso8601String(),
        'attempts': attempts,
      };

  factory QueuedAction.fromJson(Map<String, dynamic> j) => QueuedAction(
        id: j['id'] as String,
        type: j['type'] as String,
        payload: (j['payload'] as Map).cast<String, dynamic>(),
        createdAt: DateTime.parse(j['createdAt'] as String),
        attempts: j['attempts'] as int? ?? 0,
      );
}
