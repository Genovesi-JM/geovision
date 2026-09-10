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
  String get backendProviderId => 'fake';
  @override
  bool get requiresCredentials => false;

  @override
  Future<String?> register() async => 'mock-device-token';

  @override
  Stream<PushMessage> get onNotificationTap => _controller.stream;

  void emitSampleNotification(
          [String notificationId = 'notification-report-ready']) =>
      _controller.add(PushMessage(notificationId: notificationId));

  void dispose() => _controller.close();
}
