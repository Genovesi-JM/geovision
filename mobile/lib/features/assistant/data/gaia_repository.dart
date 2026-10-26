import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/networking/api_client.dart';
import '../../alerts/data/alerts_repository.dart';
import '../../account/data/customer_experience_repository.dart';
import '../../assets/data/assets_repository.dart';
import '../../devices/data/devices_repository.dart';
import '../../orders/data/orders_repository.dart';
import '../../work/data/work_repository.dart';

class GaiaMessage {
  const GaiaMessage({required this.role, required this.content});
  final String role;
  final String content;

  Map<String, String> toJson() => {'role': role, 'content': content};
}

class GaiaRepository {
  const GaiaRepository(this._api, this._ref);
  final ApiClient _api;
  final Ref _ref;

  Future<String> send(
    List<GaiaMessage> messages, {
    String? language,
    String? siteId,
    String? productId,
    String? deviceId,
    String sourcePage = 'assistant',
  }) async {
    final appContext = await _buildAppContext(
      siteId: siteId,
      productId: productId,
      deviceId: deviceId,
      sourcePage: sourcePage,
    );
    final response = await _api.raw.post<Map<String, dynamic>>(
      '/ai/chat',
      data: {
        'messages': messages.map((message) => message.toJson()).toList(),
        'page': '/mobile/$sourcePage',
        'page_title': 'GeoVision mobile · $sourcePage',
        'page_text': 'Preferred language: ${language ?? 'pt'}.\n$appContext',
      },
    );
    final reply = response.data?['reply']?.toString().trim();
    if (reply == null || reply.isEmpty) {
      throw StateError('The assistant returned an empty response.');
    }
    return reply;
  }

  Future<String> _buildAppContext({
    String? siteId,
    String? productId,
    String? deviceId,
    required String sourcePage,
  }) async {
    final experience = await _ref.read(customerExperienceProvider.future);
    final workspace = experience.activeWorkspaceId;
    final lines = <String>[
      'AUTHORIZED APP CONTEXT (customer-visible data only)',
      'Workspace: ${experience.activeWorkspace?.name ?? 'none selected'}',
      'Sector: ${experience.activeWorkspace?.sector ?? 'not specified'}',
      'Current section: $sourcePage',
      'Context assembled at: ${DateTime.now().toUtc().toIso8601String()}. This is not a measurement timestamp.',
    ];
    Future<T?> optional<T>(String source, Future<T> Function() fetch) async {
      try {
        return await fetch();
      } on DioException catch (error) {
        if (error.response?.statusCode == 401 ||
            error.response?.statusCode == 403) {
          rethrow;
        }
        lines.add(
            'Unavailable context source: $source. Do not infer its values.');
        return null;
      } catch (_) {
        lines.add(
            'Unavailable context source: $source. Do not infer its values.');
        return null;
      }
    }

    final assets = await optional(
        'assets', () => _ref.read(assetsRepositoryProvider).list());
    final devices = await optional(
        'devices', () => _ref.read(devicesRepositoryProvider).getDevices());
    final device = devices?.where((d) => d.id == deviceId).firstOrNull;
    final selectedId = siteId ?? device?.assetId;
    final asset = assets?.value.where((a) => a.id == selectedId).firstOrNull;
    if (assets != null) {
      lines.add(
          'Assets source: ${assets.fromCache ? 'cached' : 'server'}; synced ${assets.syncedAt?.toIso8601String() ?? 'unknown'}.');
    }
    if (asset != null) {
      lines.add(
          'Selected asset: ${asset.id} | ${asset.name} | ${asset.sector} | ${asset.locationLabel}.');
    } else {
      lines.add(
          'No verified asset selected. Ask the customer to select a location before giving location-specific advice. Never choose the first asset.');
    }
    if (deviceId != null && device == null) {
      lines.add(
          'Requested device is unavailable in this workspace. Do not substitute another device.');
    }
    if (device != null && siteId != null && device.assetId != siteId) {
      throw StateError('The device does not belong to the selected asset.');
    }
    final relevantDevices = deviceId != null
        ? (devices ?? []).where((d) => d.id == deviceId)
        : (devices ?? []).where((d) => asset != null && d.assetId == asset.id);
    for (final d in relevantDevices.take(8)) {
      lines.add(
          'Device: ${d.id} | ${d.name} | ${d.siteName} | ${d.status} | battery ${d.batteryPercent == null ? 'unknown' : '${d.batteryPercent}%'} | reading ${d.lastReadingLabel ?? 'unavailable'} | measured at ${d.lastReadingAt?.toUtc().toIso8601String() ?? 'unknown'}.');
    }
    if (asset != null) {
      final alerts = await optional(
          'alerts', () => _ref.read(alertsRepositoryProvider).getAlerts());
      if (alerts != null) {
        lines.add(
            'Alerts source: ${alerts.fromCache ? 'cached' : 'server'}; synced ${alerts.syncedAt?.toIso8601String() ?? 'unknown'}.');
        for (final a in alerts.value
            .where((a) => a.siteId == asset.id && !a.resolved)
            .take(6)) {
          lines.add(
              'Alert: ${a.title} | ${a.severity} | ${a.recommendation ?? 'no recommendation recorded'}.');
        }
      }
      final requests = await optional('service requests',
          () => _ref.read(workRepositoryProvider).getRequests());
      for (final request
          in (requests ?? []).where((r) => r.siteId == asset.id).take(5)) {
        lines.add(
            'Service request: ${request.id} | ${request.type} | ${request.status}.');
      }
    }
    if (productId != null) {
      final products = await optional(
          'catalogue', () => _ref.read(ordersRepositoryProvider).catalogue());
      final product = products?.where((p) => p.id == productId).firstOrNull;
      lines.add(product == null
          ? 'Requested product unavailable. Do not invent price or availability.'
          : 'Selected product: ${product.id} | ${product.name} | ${product.description} | includes ${product.deliverables.join(', ')}.');
    }
    if (_ref.read(customerExperienceProvider).valueOrNull?.activeWorkspaceId !=
        workspace) {
      throw StateError(
          'Workspace changed. Start a new question in the selected workspace.');
    }
    lines.add(
        'Use only these facts for customer-specific answers. Cite the device/asset and measurement time. Cached or old data is not a live state. Explain missing evidence. Do not promise planned features, execute commands or claim a physical action occurred.');
    return lines.join('\n');
  }
}

final gaiaRepositoryProvider = Provider<GaiaRepository>(
  (ref) => GaiaRepository(ref.watch(apiClientProvider), ref),
);
