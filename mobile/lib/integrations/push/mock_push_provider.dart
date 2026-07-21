import 'dart:async';
import 'push_provider.dart';

/// Credential-free push. Emits a sample alert notification after launch so the
/// deep-link routing can be demonstrated end-to-end.
class MockPushProvider implements PushProvider {
  MockPushProvider();
  final _controller = StreamController<PushMessage>.broadcast();

  @override
  String get id => 'mock';
  @override
  bool get requiresCredentials => false;

  @override
  Future<String?> register() async => 'mock-device-token';

  @override
  Stream<PushMessage> get onMessage => _controller.stream;

  void emitSampleAlert() => _controller.add(const PushMessage(
        title: 'Critical alert',
        body: 'Irrigation failure — Block A',
        deepLink: '/alerts/al-1',
      ));

  void dispose() => _controller.close();
}
