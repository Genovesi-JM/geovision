import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/core/storage/offline_queue.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('enqueues, tracks attempts and removes without data loss', () async {
    final prefs = await SharedPreferences.getInstance();
    final q = OfflineQueue(prefs);

    expect(q.pendingCount, 0);
    final a = await q.enqueue('service_request', {'x': 1});
    expect(q.pendingCount, 1);

    await q.markAttempt(a.id);
    expect(q.readAll().first.attempts, 1);

    await q.remove(a.id);
    expect(q.pendingCount, 0);
  });

  test('survives reload (durable persistence)', () async {
    final prefs = await SharedPreferences.getInstance();
    final q1 = OfflineQueue(prefs);
    await q1.enqueue('service_request', {'y': 2});

    final q2 = OfflineQueue(prefs);
    expect(q2.pendingCount, 1);
    expect(q2.readAll().first.payload['y'], 2);
  });
}
