import 'package:flutter/services.dart';

import 'push_provider.dart';

/// Narrow boundary to the signed iOS/Android host application.
///
/// The host owns APNs/FCM permission and token lifecycle. Missing native
/// support, denied permission, malformed tokens, and channel failures all
/// return null so a live build never falls back to a demo endpoint.
class NativePushProvider implements PushProvider {
  const NativePushProvider(
    this.id, {
    MethodChannel methodChannel =
        const MethodChannel('com.geovision.notifications/push'),
    EventChannel eventChannel =
        const EventChannel('com.geovision.notifications/push_taps'),
  })  : _methodChannel = methodChannel,
        _eventChannel = eventChannel;

  @override
  final String id;

  final MethodChannel _methodChannel;
  final EventChannel _eventChannel;

  @override
  String get backendProviderId => 'azure_notification_hubs';

  @override
  bool get requiresCredentials => true;

  @override
  Future<String?> register() async {
    if (!const {'apns', 'fcm', 'azure_notification_hubs'}.contains(id)) {
      return null;
    }
    try {
      final response = await _methodChannel.invokeMethod<Object?>(
        'requestToken',
        {'provider': id},
      );
      final token = response is Map
          ? response['token']?.toString().trim()
          : response?.toString().trim();
      if (token == null || token.length < 16 || token.length > 4096) {
        return null;
      }
      return token;
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  @override
  Stream<PushMessage> get onNotificationTap => _eventChannel
      .receiveBroadcastStream()
      .map((payload) => payload is Map
          ? PushMessage.tryFromPayload(Map<String, dynamic>.from(payload))
          : null)
      .where((message) => message != null)
      .cast<PushMessage>();
}
