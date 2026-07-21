import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/devices_repository.dart';
import '../domain/device.dart';
import '../../../integrations/iot/iot_provider.dart';
import '../../../l10n/app_localizations.dart';

class DevicesScreen extends ConsumerWidget {
  const DevicesScreen({super.key});

  Color _statusColor(String s) {
    switch (s) {
      case 'online':
        return GvColors.accentGreen;
      case 'maintenance':
        return GvColors.medium;
      case 'pairing':
        return GvColors.info;
      case 'credentials_required':
        return GvColors.high;
      case 'unsupported':
      case 'error':
        return GvColors.critical;
      default:
        return GvColors.textMuted;
    }
  }

  String _statusLabel(BuildContext context, String status) {
    final text = AppLocalizations.of(context);
    return switch (status) {
      'online' => text.deviceOnline,
      'offline' => text.deviceOffline,
      'maintenance' => text.deviceMaintenance,
      'pairing' => text.devicePairing,
      'credentials_required' => text.deviceNeedsCredentials,
      'unsupported' => text.deviceUnsupported,
      'error' => text.deviceError,
      'demo' => text.deviceDemo,
      _ => status,
    };
  }

  IconData _typeIcon(String t) {
    switch (t) {
      case 'weather_station':
        return Icons.cloud_outlined;
      case 'gps_collar':
        return Icons.pets;
      case 'thermal':
        return Icons.thermostat;
      default:
        return Icons.sensors;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(devicesProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(AppLocalizations.of(context).devices),
        actions: [
          IconButton(
            tooltip: 'Guias visuais',
            onPressed: () => context.go('/guides'),
            icon: const Icon(Icons.menu_book_outlined),
          ),
        ],
      ),
      body: async.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(message: '$e'),
        data: (devices) => ListView.separated(
          padding: const EdgeInsets.all(GvSpacing.lg),
          itemCount: devices.length,
          separatorBuilder: (_, __) => const SizedBox(height: GvSpacing.sm),
          itemBuilder: (c, i) {
            final d = devices[i];
            return GvCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(_typeIcon(d.type), color: _statusColor(d.status)),
                      const SizedBox(width: GvSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(d.name,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                            Text(d.siteName,
                                style: const TextStyle(
                                    color: GvColors.textMuted, fontSize: 12)),
                          ],
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: _statusColor(d.status).withValues(alpha: 0.16),
                          borderRadius:
                              BorderRadius.circular(GvSpacing.radiusPill),
                        ),
                        child: Text(_statusLabel(context, d.status),
                            style: TextStyle(
                                color: _statusColor(d.status),
                                fontSize: 10,
                                fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ),
                  const SizedBox(height: GvSpacing.md),
                  Row(
                    children: [
                      _Metric(
                          icon: Icons.battery_full,
                          label: '${d.batteryPercent}%'),
                      _Metric(
                          icon: Icons.signal_cellular_alt,
                          label: '${d.signalPercent}%'),
                      if (d.lastReadingAt != null)
                        _Metric(
                            icon: Icons.schedule,
                            label: DateFormat.Hm()
                                .format(d.lastReadingAt!.toLocal())),
                    ],
                  ),
                  if (d.lastReadingLabel != null) ...[
                    const SizedBox(height: GvSpacing.sm),
                    Text(d.lastReadingLabel!,
                        style: const TextStyle(
                            color: GvColors.accentSky, fontSize: 12)),
                  ],
                  if (d.integrationMessage != null) ...[
                    const SizedBox(height: GvSpacing.sm),
                    Text(d.integrationMessage!,
                        style: const TextStyle(
                            color: GvColors.textMuted, fontSize: 11)),
                  ],
                  const SizedBox(height: GvSpacing.sm),
                  Wrap(spacing: 6, runSpacing: 6, children: [
                    Chip(
                        avatar: const Icon(Icons.hub_outlined, size: 14),
                        label: Text(d.transport.toUpperCase())),
                    ...d.capabilities.take(3).map((capability) => Chip(
                        label: Text(capability),
                        visualDensity: VisualDensity.compact)),
                  ]),
                  const SizedBox(height: GvSpacing.sm),
                  Row(children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _diagnose(context, ref, d.id),
                        icon: const Icon(Icons.health_and_safety_outlined),
                        label: Text(AppLocalizations.of(context).diagnose),
                      ),
                    ),
                    if (d.status == 'pairing' ||
                        d.status == 'credentials_required') ...[
                      const SizedBox(width: 8),
                      IconButton.filledTonal(
                        tooltip: AppLocalizations.of(context).configure,
                        onPressed: () => _configure(context, ref, d),
                        icon: const Icon(Icons.settings_input_antenna),
                      ),
                    ],
                  ]),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Future<void> _diagnose(
      BuildContext context, WidgetRef ref, String deviceId) async {
    final result = await ref.read(devicesRepositoryProvider).diagnose(deviceId);
    if (!context.mounted) return;
    await _showOutcome(context, result);
  }

  Future<void> _configure(
      BuildContext context, WidgetRef ref, GvDevice device) async {
    final transport = switch (device.transport) {
      'mqtt' => IotTransport.mqtt,
      'webhook' => IotTransport.webhook,
      'ble' => IotTransport.bluetooth,
      'lorawan' => IotTransport.lorawan,
      'modbus_gateway' => IotTransport.modbusGateway,
      _ => IotTransport.api,
    };
    final result = await ref.read(devicesRepositoryProvider).provision(
          DeviceProvisioningRequest(
            deviceId: device.id,
            transport: transport,
            siteId: device.siteName,
          ),
        );
    if (!context.mounted) return;
    await _showOutcome(context, result);
  }

  Future<void> _showOutcome(
      BuildContext context, IotOperationResult result) async {
    final color = result.succeeded ? GvColors.accentGreen : GvColors.high;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        icon: Icon(
          result.succeeded ? Icons.check_circle : Icons.info_outline,
          color: color,
        ),
        title: Text(result.outcome.name),
        content: Text(result.message ?? 'No additional information.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('OK')),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.icon, required this.label});
  final IconData icon;
  final String label;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(right: GvSpacing.lg),
        child: Row(children: [
          Icon(icon, size: 14, color: GvColors.textMuted),
          const SizedBox(width: 4),
          Text(label,
              style:
                  const TextStyle(color: GvColors.textSecondary, fontSize: 12)),
        ]),
      );
}
