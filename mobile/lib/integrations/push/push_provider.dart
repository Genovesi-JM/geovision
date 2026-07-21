/// Abstract push contract. Alerts are generated + stored by the backend; the
/// app only registers a device token and routes taps to deep links. Concrete
/// providers: mock, APNs, FCM.
abstract interface class PushProvider {
  String get id;
  bool get requiresCredentials;
  Future<String?> register();
  Stream<PushMessage> get onMessage;
}

class PushMessage {
  const PushMessage({required this.title, required this.body, this.deepLink});
  final String title;
  final String body;
  final String? deepLink; // e.g. /alerts/al-1
}
