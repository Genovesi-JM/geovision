import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/networking/api_client.dart';
import '../../alerts/data/alerts_repository.dart';
import '../../devices/data/devices_repository.dart';
import '../../orders/data/orders_repository.dart';
import '../../sites/data/sites_repository.dart';
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
    String sourcePage = 'assistant',
  }) async {
    final appContext = await _buildAppContext(
      siteId: siteId,
      productId: productId,
      sourcePage: sourcePage,
    );
    final response = await _api.raw.post<Map<String, dynamic>>(
      '/ai/chat',
      data: {
        'messages': messages.map((message) => message.toJson()).toList(),
        'page': '/mobile/$sourcePage',
        'page_title': 'GeoVision mobile · $sourcePage',
        'sector': 'Geral',
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
    required String sourcePage,
  }) async {
    final sites = (await _ref.read(sitesRepositoryProvider).getSites()).value;
    final alerts =
        (await _ref.read(alertsRepositoryProvider).getAlerts()).value;
    final devices = await _ref.read(devicesRepositoryProvider).getDevices();
    final requests = await _ref.read(workRepositoryProvider).getRequests();
    final products = await _ref.read(ordersRepositoryProvider).catalogue();

    final selectedId = siteId ?? _ref.read(selectedSiteIdProvider);
    final selected = sites.where((item) => item.id == selectedId).firstOrNull ??
        (sites.isEmpty ? null : sites.first);
    final selectedProduct =
        products.where((item) => item.id == productId).firstOrNull;

    final lines = <String>[
      'AUTHORIZED APP CONTEXT (customer-visible data only)',
      'Current section: $sourcePage',
      'Totals: ${sites.length} sites, ${alerts.where((a) => !a.resolved).length} open alerts, ${devices.length} devices, ${requests.where((r) => r.status != 'completed').length} active service requests.',
    ];
    if (selected != null) {
      lines.add(
          'Selected site: ${selected.name} | ${selected.location} | ${selected.totalHectares.toStringAsFixed(1)} ha | status ${selected.status.name}.');
      for (final area in selected.areas.take(8)) {
        final kpis = area.kpis
            .take(4)
            .map((k) => '${k.label} ${k.value}${k.unit ?? ''} (${k.status})')
            .join(', ');
        lines.add(
            'Area: ${area.name} | crop ${area.crop} | ${area.hectares.toStringAsFixed(1)} ha${kpis.isEmpty ? '' : ' | $kpis'}.');
      }
      final siteKpis = selected.kpis
          .take(8)
          .map((k) =>
              '${k.label}=${k.value}${k.unit ?? ''} (${k.status}, ${k.trend})')
          .join('; ');
      if (siteKpis.isNotEmpty) lines.add('Site KPIs: $siteKpis.');
    }
    for (final alert in alerts.where((item) => !item.resolved).take(6)) {
      lines.add(
          'Alert: ${alert.title} | ${alert.severity} | ${alert.location ?? alert.siteId ?? 'site unknown'} | recommendation ${alert.recommendation ?? 'not recorded'}.');
    }
    for (final device in devices.take(6)) {
      lines.add(
          'Device: ${device.name} | ${device.siteName} | ${device.status} | battery ${device.batteryPercent}% | latest ${device.lastReadingLabel ?? 'not available'}.');
    }
    for (final request in requests.take(5)) {
      lines.add(
          'Service request: ${request.type} | ${request.siteName} | ${request.status} | progress ${request.progressPercent}%.');
    }
    if (selectedProduct != null) {
      lines.add(
          'Open product: ${selectedProduct.name} | ${selectedProduct.category} | ${selectedProduct.description} | includes ${selectedProduct.deliverables.join(', ')}.');
    }
    lines.add(
        'Answer from these facts first. If a requested value is absent, say it is not recorded; never invent it.');
    return lines.join('\n');
  }
}

final gaiaRepositoryProvider = Provider<GaiaRepository>(
  (ref) => GaiaRepository(ref.watch(apiClientProvider), ref),
);
