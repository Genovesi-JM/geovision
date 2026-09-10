/// Abstract push contract. Notifications are generated and stored by the
/// backend. Provider payloads expose only an opaque notification id; the app
/// asks the backend to authorize and resolve the contextual destination.
abstract interface class PushProvider {
  String get id;
  String get backendProviderId;
  bool get requiresCredentials;
  Future<String?> register();
  Stream<PushMessage> get onNotificationTap;
}

class PushMessage {
  const PushMessage({required this.notificationId});

  final String notificationId;

  static PushMessage? tryFromPayload(Map<String, dynamic> payload) {
    final id = payload['notification_id']?.toString().trim() ?? '';
    if (!RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(id)) return null;
    return PushMessage(notificationId: id);
  }
}

/// Fail-closed placeholder used until a credentialed native adapter is wired.
class UnavailablePushProvider implements PushProvider {
  const UnavailablePushProvider(this.id);

  @override
  final String id;

  @override
  String get backendProviderId => '';

  @override
  bool get requiresCredentials => true;

  @override
  Future<String?> register() async => null;

  @override
  Stream<PushMessage> get onNotificationTap => const Stream.empty();
}
