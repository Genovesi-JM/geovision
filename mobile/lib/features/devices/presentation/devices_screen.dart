import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/devices_repository.dart';

class DevicesScreen extends ConsumerWidget {
  const DevicesScreen({super.key});

  Color _statusColor(String s) {
    switch (s) {
      case 'online':
        return GvColors.accentGreen;
      case 'maintenance':
        return GvColors.medium;
      default:
        return GvColors.textMuted;
    }
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
      appBar: AppBar(title: const Text('Devices')),
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
                        child: Text(d.status,
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
                ],
              ),
            );
          },
        ),
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
