import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// Honest connectivity + freshness indicator. When offline we NEVER imply the
/// data is live — we show the last synchronised time instead.
class SyncBanner extends StatelessWidget {
  const SyncBanner({super.key, required this.online, this.lastSyncedAt});
  final bool online;
  final DateTime? lastSyncedAt;

  @override
  Widget build(BuildContext context) {
    final color = online ? GvColors.accentGreen : GvColors.medium;
    final label = online ? 'Online' : 'Offline — showing last synced data';
    final ts = lastSyncedAt == null
        ? ''
        : ' · ${DateFormat.MMMd().add_Hm().format(lastSyncedAt!.toLocal())}';
    return Container(
      width: double.infinity,
      padding:
          const EdgeInsets.symmetric(horizontal: GvSpacing.lg, vertical: 6),
      color: color.withValues(alpha: 0.12),
      child: Row(
        children: [
          Icon(online ? Icons.cloud_done_outlined : Icons.cloud_off_outlined,
              size: 14, color: color),
          const SizedBox(width: 6),
          Expanded(
            child: Text('$label$ts',
                style: TextStyle(
                    color: color, fontSize: 11, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}
