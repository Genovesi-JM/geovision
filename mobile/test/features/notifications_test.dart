import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/errors/failures.dart';
import 'package:geovision/core/errors/result.dart';
import 'package:geovision/features/notifications/data/notifications_repository.dart';
import 'package:geovision/features/notifications/domain/notification.dart';
import 'package:geovision/features/notifications/presentation/notifications_screen.dart';
import 'package:geovision/integrations/push/native_push_provider.dart';
import 'package:geovision/integrations/push/push_provider.dart';
import 'package:go_router/go_router.dart';

class _FakeNotifications implements NotificationsGateway {
  _FakeNotifications(this.notification);

  GvNotification notification;
  int markReadCalls = 0;
  int resolveCalls = 0;

  @override
  Future<Result<NotificationPage>> loadInbox({
    bool unreadOnly = false,
    String? category,
  }) async =>
      Ok(NotificationPage(
        items: unreadOnly && notification.isRead ? [] : [notification],
        total: 1,
        unread: notification.isRead ? 0 : 1,
      ));

  @override
  Future<Result<GvNotification>> markRead(String notificationId) async {
    markReadCalls++;
    notification = notification.copyWith(readAt: DateTime.utc(2026, 9, 10));
    return Ok(notification);
  }

  @override
  Future<Result<NotificationTarget>> resolveTarget(
      String notificationId) async {
    resolveCalls++;
    return Ok(NotificationTarget(
      notificationId: notificationId,
      type: 'REPORT',
      id: 'report-42',
      appPath: '/reports/report-42',
    ));
  }

  @override
  Future<Result<void>> markAllRead({String? organizationId}) async =>
      const Ok(null);

  @override
  Future<Result<int>> unreadCount() async => Ok(notification.isRead ? 0 : 1);

  @override
  Future<Result<List<NotificationPreference>>> loadPreferences() async =>
      Ok(notificationCategories.map(NotificationPreference.defaults).toList());

  @override
  Future<Result<NotificationPreference>> savePreference(
          NotificationPreference preference) async =>
      Ok(preference);

  @override
  Future<Result<NotificationContextDetails>> loadContextDetails(
          String type, String id) async =>
      Ok(NotificationContextDetails(
          type: type, id: id, title: 'Target', status: 'Available'));

  @override
  Future<Result<void>> registerEndpoint({
    required String installationId,
    required String platform,
    required String provider,
    required String handle,
  }) async =>
      const Ok(null);

  @override
  Future<Result<void>> registerCurrentEndpoint({
    required String provider,
    required String handle,
  }) async =>
      const Ok(null);

  @override
  Future<Result<void>> revokeEndpoint(String installationId) async =>
      const Ok(null);
}

GvNotification _notification() => GvNotification(
      id: 'notification-1',
      organizationId: 'organization-1',
      category: 'REPORT',
      type: 'report.published',
      title: 'Your results are ready',
      body: 'Open the published report.',
      severity: 'INFO',
      targetType: 'REPORT',
      targetId: 'report-42',
      occurrenceCount: 1,
      firstOccurredAt: DateTime.utc(2026, 9, 10, 8),
      lastOccurredAt: DateTime.utc(2026, 9, 10, 8),
      createdAt: DateTime.utc(2026, 9, 10, 8),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('safe target validation binds type, id, and exact app route', () {
    expect(isSafeNotificationAppPath('/portal'), isTrue);
    expect(isSafeNotificationAppPath('/orders/order-1'), isTrue);
    expect(
        isSafeNotificationAppPath('/reports/report-1?download=true'), isFalse);
    expect(isSafeNotificationAppPath('https://evil.test/reports/report-1'),
        isFalse);

    expect(
      isSafeNotificationTarget(const NotificationTarget(
        notificationId: 'n-1',
        type: 'REPORT',
        id: 'report-1',
        appPath: '/reports/report-1',
      )),
      isTrue,
    );
    expect(
      isSafeNotificationTarget(const NotificationTarget(
        notificationId: 'n-1',
        type: 'REPORT',
        id: 'report-1',
        appPath: '/assets/report-1',
      )),
      isFalse,
    );
    expect(
      isSafeNotificationTarget(const NotificationTarget(
        notificationId: 'n-2',
        type: 'INVITATION',
        id: 'invite-1',
        appPath: '/portal',
      )),
      isTrue,
    );
  });

  test('push payload parser retains only an opaque notification id', () {
    final message = PushMessage.tryFromPayload({
      'notification_id': 'notification-123',
      'deep_link': 'https://evil.test/steal',
      'title': 'Untrusted title',
    });
    expect(message?.notificationId, 'notification-123');
    expect(
        PushMessage.tryFromPayload(
            {'notification_id': '../../reports/private'}),
        isNull);
    expect(PushMessage.tryFromPayload({'deep_link': '/reports/r-1'}), isNull);
  });

  test('preference contract preserves optional SMS and quiet hours', () {
    final preference = NotificationPreference.fromJson({
      'category': 'device',
      'in_app_enabled': true,
      'push_enabled': false,
      'email_enabled': true,
      'sms_enabled': true,
      'minimum_severity': 'warning',
      'quiet_hours_start': '22:00',
      'quiet_hours_end': '06:00',
      'timezone': 'Europe/Madrid',
    });
    expect(preference.category, 'DEVICE');
    expect(preference.smsEnabled, isTrue);
    expect(preference.quietHoursStart, '22:00');
    expect(preference.toJson()['quiet_hours_end'], '06:00');
  });

  test('native token boundary accepts valid tokens and fails closed', () async {
    const channel = MethodChannel('geovision.test/push');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'requestToken');
      return {'token': 'native-token-at-least-sixteen'};
    });
    const provider = NativePushProvider(
      'apns',
      methodChannel: channel,
      eventChannel: EventChannel('geovision.test/push-events'),
    );
    expect(await provider.register(), 'native-token-at-least-sixteen');
    expect(provider.backendProviderId, 'azure_notification_hubs');

    messenger.setMockMethodCallHandler(
        channel, (_) async => throw PlatformException(code: 'denied'));
    expect(await provider.register(), isNull);
    messenger.setMockMethodCallHandler(channel, null);
    expect(await provider.register(), isNull,
        reason: 'A missing signed native integration must stay disabled.');
  });

  testWidgets(
      'inbox tap marks read then navigates only through resolved target',
      (tester) async {
    final gateway = _FakeNotifications(_notification());
    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (_, __) => const NotificationsScreen()),
        GoRoute(
          path: '/reports/:id',
          builder: (_, state) => Text('opened:${state.pathParameters['id']}'),
        ),
      ],
    );
    addTearDown(router.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          notificationsRepositoryProvider.overrideWithValue(gateway),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Your results are ready'), findsOneWidget);

    await tester.tap(find.text('Your results are ready'));
    await tester.pumpAndSettle();

    expect(gateway.markReadCalls, 1);
    expect(gateway.resolveCalls, 1);
    expect(find.text('opened:report-42'), findsOneWidget);
  });

  test('fake gateway can expose typed failures without throwing', () async {
    const failure = ValidationFailure('unsafe');
    const result = Err<NotificationTarget>(failure);
    expect(result.isOk, isFalse);
    expect(result.valueOrNull, isNull);
  });
}
