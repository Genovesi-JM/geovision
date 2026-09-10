import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/errors/failures.dart';
import '../../../core/errors/result.dart';
import '../../../core/networking/api_client.dart';
import '../domain/notification.dart';

abstract interface class NotificationsGateway {
  Future<Result<NotificationPage>> loadInbox({
    bool unreadOnly = false,
    String? category,
  });

  Future<Result<int>> unreadCount();
  Future<Result<GvNotification>> markRead(String notificationId);
  Future<Result<void>> markAllRead({String? organizationId});
  Future<Result<NotificationTarget>> resolveTarget(String notificationId);
  Future<Result<List<NotificationPreference>>> loadPreferences();
  Future<Result<NotificationPreference>> savePreference(
      NotificationPreference preference);
  Future<Result<NotificationContextDetails>> loadContextDetails(
      String type, String id);
  Future<Result<void>> registerEndpoint({
    required String installationId,
    required String platform,
    required String provider,
    required String handle,
  });
  Future<Result<void>> registerCurrentEndpoint({
    required String provider,
    required String handle,
  });
  Future<Result<void>> revokeEndpoint(String installationId);
}

class NotificationsRepository implements NotificationsGateway {
  NotificationsRepository(this._api, this._config, this._preferences) {
    if (_config.demoMode) _seedDemo();
  }

  final ApiClient _api;
  final AppConfig _config;
  final SharedPreferences _preferences;
  final List<GvNotification> _demoNotifications = [];
  final Map<String, NotificationPreference> _demoPreferences = {};

  static const _installationKey = 'gv_notification_installation_id';

  String get installationId {
    final saved = _preferences.getString(_installationKey);
    if (saved != null && saved.isNotEmpty) return saved;
    final entropy = Random.secure().nextInt(0x7fffffff).toRadixString(36);
    final generated =
        'mobile_${DateTime.now().microsecondsSinceEpoch}_$entropy';
    _preferences.setString(_installationKey, generated);
    return generated;
  }

  String get endpointPlatform => switch (defaultTargetPlatform) {
        TargetPlatform.iOS => 'IOS',
        TargetPlatform.android => 'ANDROID',
        _ => 'WEB',
      };

  @override
  Future<Result<NotificationPage>> loadInbox({
    bool unreadOnly = false,
    String? category,
  }) async {
    if (category != null && !notificationCategories.contains(category)) {
      return const Err(ValidationFailure('Invalid notification category.'));
    }
    if (_config.demoMode) {
      final rows = _demoNotifications
          .where((item) => !unreadOnly || !item.isRead)
          .where((item) => category == null || item.category == category)
          .toList(growable: false);
      return Ok(NotificationPage(
        items: rows,
        total: rows.length,
        unread: rows.where((item) => !item.isRead).length,
      ));
    }
    try {
      final response = await _api.raw.get('/notifications', queryParameters: {
        'unread_only': unreadOnly,
        if (category != null) 'category': category,
      });
      return Ok(NotificationPage.fromJson(
          Map<String, dynamic>.from(response.data as Map)));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<int>> unreadCount() async {
    if (_config.demoMode) {
      return Ok(_demoNotifications.where((item) => !item.isRead).length);
    }
    try {
      final response = await _api.raw.get('/notifications/unread-count');
      final body = Map<String, dynamic>.from(response.data as Map);
      return Ok((body['unread'] as num?)?.toInt() ?? 0);
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<GvNotification>> markRead(String notificationId) async {
    if (!_safeId(notificationId)) {
      return const Err(ValidationFailure('Invalid notification.'));
    }
    if (_config.demoMode) {
      final index =
          _demoNotifications.indexWhere((n) => n.id == notificationId);
      if (index < 0) {
        return const Err(
            ServerFailure('Notification no longer exists.', statusCode: 404));
      }
      _demoNotifications[index] =
          _demoNotifications[index].copyWith(readAt: DateTime.now().toUtc());
      return Ok(_demoNotifications[index]);
    }
    try {
      final response =
          await _api.raw.post('/notifications/$notificationId/read');
      return Ok(GvNotification.fromJson(
          Map<String, dynamic>.from(response.data as Map)));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<void>> markAllRead({String? organizationId}) async {
    if (_config.demoMode) {
      for (var index = 0; index < _demoNotifications.length; index++) {
        if (!_demoNotifications[index].isRead) {
          _demoNotifications[index] = _demoNotifications[index]
              .copyWith(readAt: DateTime.now().toUtc());
        }
      }
      return const Ok(null);
    }
    try {
      await _api.raw.post('/notifications/read-all', queryParameters: {
        if (organizationId != null) 'organization_id': organizationId,
      });
      return const Ok(null);
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<NotificationTarget>> resolveTarget(
      String notificationId) async {
    if (!_safeId(notificationId)) {
      return const Err(ValidationFailure('Invalid notification.'));
    }
    if (_config.demoMode) {
      final notification =
          _demoNotifications.where((n) => n.id == notificationId).firstOrNull;
      if (notification == null || notification.targetId == null) {
        return const Err(ServerFailure('This notification has no destination.',
            statusCode: 404));
      }
      final path = switch (notification.targetType) {
        'ASSET' => '/assets/${notification.targetId}',
        'REPORT' => '/reports/${notification.targetId}',
        'ACTION' => '/actions/${notification.targetId}',
        'ORDER' || 'SHIPMENT' => '/orders/${notification.targetId}',
        'SERVICE' => '/services/${notification.targetId}',
        'INVITATION' => '/portal',
        _ => '',
      };
      final target = NotificationTarget(
        notificationId: notification.id,
        type: notification.targetType,
        id: notification.targetId!,
        workspaceId: notification.workspaceId,
        appPath: path,
      );
      return isSafeNotificationTarget(target)
          ? Ok(target)
          : const Err(ValidationFailure('Unsafe notification destination.'));
    }
    try {
      final response =
          await _api.raw.get('/notifications/$notificationId/target');
      final target = NotificationTarget.fromJson(
          Map<String, dynamic>.from(response.data as Map));
      if (!isSafeNotificationTarget(target)) {
        return const Err(ValidationFailure(
            'The notification destination could not be verified.'));
      }
      return Ok(target);
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<List<NotificationPreference>>> loadPreferences() async {
    if (_config.demoMode) {
      return Ok(notificationCategories
          .map((category) => _demoPreferences[category]!)
          .toList(growable: false));
    }
    try {
      final response = await _api.raw.get('/notification-preferences');
      final body = Map<String, dynamic>.from(response.data as Map);
      final rows = body['items'] as List? ?? const [];
      final explicit = <String, NotificationPreference>{
        for (final row in rows.whereType<Map>())
          '${row['category']}'.toUpperCase():
              NotificationPreference.fromJson(Map<String, dynamic>.from(row)),
      };
      return Ok(notificationCategories
          .map((category) =>
              explicit[category] ?? NotificationPreference.defaults(category))
          .toList(growable: false));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<NotificationPreference>> savePreference(
      NotificationPreference preference) async {
    if (!notificationCategories.contains(preference.category) ||
        !const {'INFO', 'WATCH', 'WARNING', 'CRITICAL'}
            .contains(preference.minimumSeverity)) {
      return const Err(ValidationFailure('Invalid notification preference.'));
    }
    if (_config.demoMode) {
      _demoPreferences[preference.category] = preference;
      return Ok(preference);
    }
    try {
      final response = await _api.raw.put(
        '/notification-preferences',
        data: preference.toJson(),
      );
      return Ok(NotificationPreference.fromJson(
          Map<String, dynamic>.from(response.data as Map)));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<NotificationContextDetails>> loadContextDetails(
      String type, String id) async {
    final normalizedType = type.toUpperCase();
    if (!_safeId(id) ||
        !const {'ASSET', 'REPORT', 'ACTION', 'SERVICE'}
            .contains(normalizedType)) {
      return const Err(ValidationFailure('Invalid notification context.'));
    }
    if (_config.demoMode) return Ok(_demoContext(normalizedType, id));
    if (normalizedType == 'SERVICE') {
      // The target endpoint already reauthorized this opaque job id. No
      // customer-facing fulfilment-detail API exists yet, so do not probe the
      // internal contractor route or expose internal scheduling fields.
      return Ok(NotificationContextDetails(
        type: normalizedType,
        id: id,
        title: 'Service update',
        status: 'Available',
        description:
            'Open your service requests for the latest customer-visible status.',
      ));
    }
    final endpoint = switch (normalizedType) {
      'ASSET' => '/assets/$id',
      'REPORT' => '/reports/$id',
      'ACTION' => '/actions/$id',
      _ => throw StateError('unreachable'),
    };
    try {
      final response = await _api.raw.get(endpoint);
      return Ok(_contextFromJson(
        normalizedType,
        id,
        Map<String, dynamic>.from(response.data as Map),
      ));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<void>> registerEndpoint({
    required String installationId,
    required String platform,
    required String provider,
    required String handle,
  }) async {
    if (_config.demoMode) return const Ok(null);
    if (!_safeId(installationId) ||
        !const {'IOS', 'ANDROID', 'WEB'}.contains(platform) ||
        !const {'azure_notification_hubs', 'fake', 'file'}.contains(provider) ||
        handle.trim().length < 16 ||
        handle.trim().length > 4096) {
      return const Err(ValidationFailure('Invalid push registration.'));
    }
    try {
      await _api.raw.put(
        '/notification-endpoints/$installationId',
        data: {
          'platform': platform,
          'provider': provider,
          'handle': handle.trim(),
        },
      );
      return const Ok(null);
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  @override
  Future<Result<void>> registerCurrentEndpoint({
    required String provider,
    required String handle,
  }) =>
      registerEndpoint(
        installationId: installationId,
        platform: endpointPlatform,
        provider: provider,
        handle: handle,
      );

  @override
  Future<Result<void>> revokeEndpoint(String installationId) async {
    if (_config.demoMode) return const Ok(null);
    if (!_safeId(installationId)) {
      return const Err(ValidationFailure('Invalid push registration.'));
    }
    try {
      await _api.raw.delete('/notification-endpoints/$installationId');
      return const Ok(null);
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  void _seedDemo() {
    final now = DateTime.now().toUtc();
    _demoNotifications.addAll([
      GvNotification(
        id: 'notification-report-ready',
        organizationId: 'demo-organization',
        workspaceId: 'demo-workspace',
        category: 'REPORT',
        type: 'report.published',
        title: 'Your results are ready',
        body: 'NDVI Health Report — Kilombo North is ready to review.',
        severity: 'INFO',
        targetType: 'REPORT',
        targetId: 'rp-1',
        occurrenceCount: 1,
        firstOccurredAt: now.subtract(const Duration(minutes: 25)),
        lastOccurredAt: now.subtract(const Duration(minutes: 25)),
        createdAt: now.subtract(const Duration(minutes: 25)),
      ),
      GvNotification(
        id: 'notification-device-offline',
        organizationId: 'demo-organization',
        workspaceId: 'demo-workspace',
        category: 'DEVICE',
        type: 'device.offline_detected',
        title: 'Asset needs attention',
        body: 'Kilombo North has not reported recent device data.',
        severity: 'WARNING',
        targetType: 'ASSET',
        targetId: 'site-1',
        occurrenceCount: 3,
        firstOccurredAt: now.subtract(const Duration(hours: 2)),
        lastOccurredAt: now.subtract(const Duration(minutes: 42)),
        createdAt: now.subtract(const Duration(hours: 2)),
      ),
      GvNotification(
        id: 'notification-order-update',
        organizationId: 'demo-organization',
        category: 'SHIPMENT',
        type: 'shipment.state_changed',
        title: 'Delivery update',
        body: 'Order GV-2405-0187 is in transit.',
        severity: 'INFO',
        targetType: 'SHIPMENT',
        targetId: 'GV-2405-0187',
        occurrenceCount: 1,
        firstOccurredAt: now.subtract(const Duration(days: 1)),
        lastOccurredAt: now.subtract(const Duration(days: 1)),
        readAt: now.subtract(const Duration(hours: 18)),
        createdAt: now.subtract(const Duration(days: 1)),
      ),
    ]);
    for (final category in notificationCategories) {
      _demoPreferences[category] = NotificationPreference.defaults(category);
    }
  }

  NotificationContextDetails _demoContext(String type, String id) {
    if (type == 'REPORT' && id == 'rp-1') {
      return const NotificationContextDetails(
        type: 'REPORT',
        id: 'rp-1',
        title: 'NDVI Health Report — Kilombo North',
        status: 'Published',
        description:
            'Fresh multispectral findings and recommended field actions.',
        facts: {'Asset': 'Kilombo North Fields', 'Type': 'NDVI'},
      );
    }
    if (type == 'ASSET' && id == 'site-1') {
      return const NotificationContextDetails(
        type: 'ASSET',
        id: 'site-1',
        title: 'Kilombo North Fields',
        status: 'Needs attention',
        description: 'Agricultural asset in Malanje, Angola.',
        facts: {'Sector': 'Agriculture', 'Open alerts': '2'},
      );
    }
    return NotificationContextDetails(
      type: type,
      id: id,
      title: _typeLabel(type),
      status: 'Available',
      description: 'Reference $id',
    );
  }

  NotificationContextDetails _contextFromJson(
      String type, String id, Map<String, dynamic> json) {
    final narrative = json['narrative'] is Map
        ? Map<String, dynamic>.from(json['narrative'] as Map)
        : const <String, dynamic>{};
    final title = '${json['title'] ?? json['name'] ?? _typeLabel(type)}';
    final description = json['description']?.toString() ??
        narrative['executive_summary']?.toString();
    final facts = <String, String>{};
    void add(String label, Object? value) {
      final text = value?.toString().trim();
      if (text != null && text.isNotEmpty) facts[label] = text;
    }

    switch (type) {
      case 'ASSET':
        add('Sector', json['sector']);
        add('Asset type', json['asset_type']);
        add('Location', json['location_label']);
      case 'REPORT':
        add('Report type', json['report_type']);
        add('Revision', json['revision']);
        add('Published', json['published_at']);
      case 'ACTION':
        add('Priority', json['priority']);
        add('Due', json['due_date']);
      case 'SERVICE':
        add('Scheduled', json['scheduled_for']);
        add('Order', json['order_id']);
    }
    return NotificationContextDetails(
      type: type,
      id: id,
      title: title,
      status: '${json['status'] ?? 'Available'}',
      description: description,
      facts: facts,
    );
  }

  static String _typeLabel(String type) => switch (type) {
        'ASSET' => 'Asset details',
        'REPORT' => 'Report details',
        'ACTION' => 'Action details',
        'SERVICE' => 'Service details',
        _ => 'Details',
      };

  static bool _safeId(String value) =>
      RegExp(r'^[A-Za-z0-9_-]{1,128}$').hasMatch(value);
}

final notificationsRepositoryProvider = Provider<NotificationsGateway>((ref) {
  return NotificationsRepository(
    ref.watch(apiClientProvider),
    ref.watch(appConfigProvider),
    ref.watch(sharedPrefsProvider),
  );
});

class NotificationInboxController
    extends StateNotifier<AsyncValue<NotificationPage>> {
  NotificationInboxController(this._repository)
      : super(const AsyncValue.loading()) {
    load();
  }

  final NotificationsGateway _repository;
  bool _unreadOnly = false;

  Future<void> load({bool? unreadOnly}) async {
    _unreadOnly = unreadOnly ?? _unreadOnly;
    state = const AsyncValue.loading();
    final result = await _repository.loadInbox(unreadOnly: _unreadOnly);
    if (!mounted) return;
    result.when(
      ok: (page) => state = AsyncValue.data(page),
      err: (failure) =>
          state = AsyncValue.error(failure.message, StackTrace.current),
    );
  }

  Future<Failure?> markRead(String notificationId) async {
    final result = await _repository.markRead(notificationId);
    Failure? failure;
    result.when(
      ok: (updated) {
        final current = state.valueOrNull;
        if (current == null) return;
        final items = current.items
            .map((item) => item.id == updated.id ? updated : item)
            .where((item) => !_unreadOnly || !item.isRead)
            .toList(growable: false);
        state = AsyncValue.data(current.copyWith(
          items: items,
          total: _unreadOnly ? items.length : current.total,
          unread: max(0, current.unread - 1),
        ));
      },
      err: (value) => failure = value,
    );
    return failure;
  }

  Future<Failure?> markAllRead() async {
    final result = await _repository.markAllRead();
    Failure? failure;
    result.when(
      ok: (_) {
        final current = state.valueOrNull;
        if (current == null) return;
        final items = _unreadOnly
            ? const <GvNotification>[]
            : current.items
                .map((item) => item.isRead
                    ? item
                    : item.copyWith(readAt: DateTime.now().toUtc()))
                .toList(growable: false);
        state = AsyncValue.data(current.copyWith(
          items: items,
          total: _unreadOnly ? 0 : current.total,
          unread: 0,
        ));
      },
      err: (value) => failure = value,
    );
    return failure;
  }
}

final notificationInboxProvider = StateNotifierProvider.autoDispose<
    NotificationInboxController, AsyncValue<NotificationPage>>((ref) {
  return NotificationInboxController(
      ref.watch(notificationsRepositoryProvider));
});

class NotificationPreferencesController
    extends StateNotifier<AsyncValue<List<NotificationPreference>>> {
  NotificationPreferencesController(this._repository)
      : super(const AsyncValue.loading()) {
    load();
  }

  final NotificationsGateway _repository;

  Future<void> load() async {
    state = const AsyncValue.loading();
    final result = await _repository.loadPreferences();
    if (!mounted) return;
    result.when(
      ok: (items) => state = AsyncValue.data(items),
      err: (failure) =>
          state = AsyncValue.error(failure.message, StackTrace.current),
    );
  }

  Future<Failure?> save(NotificationPreference preference) async {
    final previous = state.valueOrNull;
    if (previous != null) {
      state = AsyncValue.data(previous
          .map((item) =>
              item.category == preference.category ? preference : item)
          .toList(growable: false));
    }
    final result = await _repository.savePreference(preference);
    Failure? failure;
    result.when(
      ok: (saved) {
        final current = state.valueOrNull ?? const <NotificationPreference>[];
        state = AsyncValue.data(current
            .map((item) => item.category == saved.category ? saved : item)
            .toList(growable: false));
      },
      err: (value) {
        failure = value;
        if (previous != null) state = AsyncValue.data(previous);
      },
    );
    return failure;
  }
}

final notificationPreferencesProvider = StateNotifierProvider.autoDispose<
    NotificationPreferencesController,
    AsyncValue<List<NotificationPreference>>>((ref) {
  return NotificationPreferencesController(
      ref.watch(notificationsRepositoryProvider));
});

typedef NotificationContextKey = ({String type, String id});

final notificationContextProvider = FutureProvider.autoDispose
    .family<NotificationContextDetails, NotificationContextKey>(
  (ref, key) async {
    final result = await ref
        .watch(notificationsRepositoryProvider)
        .loadContextDetails(key.type, key.id);
    return result.when(
      ok: (details) => details,
      err: (failure) => throw StateError(failure.message),
    );
  },
);
