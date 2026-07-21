import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:geovision/core/storage/local_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('writes payload with a syncedAt timestamp for honest freshness',
      () async {
    final prefs = await SharedPreferences.getInstance();
    final store = LocalStore(prefs);
    await store.writeJson('sites', [
      {'id': 's1'}
    ]);
    final env = store.readJson('sites');
    expect(env, isNotNull);
    expect(env!.syncedAt, isNotNull);
    expect((env.data as List).first['id'], 's1');
  });
}
