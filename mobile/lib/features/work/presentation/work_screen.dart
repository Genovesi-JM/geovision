import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../../../l10n/app_localizations.dart';
import '../data/work_repository.dart';
import '../domain/service_request.dart';

class WorkScreen extends ConsumerWidget {
  const WorkScreen({super.key});

  Color _statusColor(String s) {
    switch (s) {
      case 'completed':
        return GvColors.accentGreen;
      case 'in_field':
      case 'processing':
        return GvColors.accentSky;
      case 'scheduled':
        return GvColors.medium;
      default:
        return GvColors.textMuted;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(serviceRequestsProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(AppLocalizations.of(context).navWork),
        actions: [
          IconButton(
            tooltip: 'Drones e missões',
            onPressed: () => context.go('/drones'),
            icon: const Icon(Icons.flight_takeoff),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.go('/work/new'),
        backgroundColor: GvColors.accentCyan,
        foregroundColor: GvColors.bgDarker,
        icon: const Icon(Icons.add),
        label: Text(AppLocalizations.of(context).newRequest),
      ),
      body: async.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(
            message: '$e', onRetry: () => ref.refresh(serviceRequestsProvider)),
        data: (requests) {
          if (requests.isEmpty) {
            return GvEmpty(
                message: AppLocalizations.of(context).noServiceRequestsYet,
                icon: Icons.work_outline);
          }
          return RefreshIndicator(
            onRefresh: () async => ref.refresh(serviceRequestsProvider.future),
            child: ListView.separated(
              padding: const EdgeInsets.all(GvSpacing.lg),
              itemCount: requests.length,
              separatorBuilder: (_, __) => const SizedBox(height: GvSpacing.sm),
              itemBuilder: (c, i) {
                final r = requests[i];
                final type = ServiceType.values.firstWhere(
                    (t) => t.name == r.type,
                    orElse: () => ServiceType.inspection);
                return GvCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(Icons.build_circle_outlined,
                              color: _statusColor(r.status), size: 20),
                          const SizedBox(width: GvSpacing.sm),
                          Expanded(
                            child: Text(type.label,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700)),
                          ),
                          if (r.pendingSync)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: GvColors.medium.withValues(alpha: 0.16),
                                borderRadius:
                                    BorderRadius.circular(GvSpacing.radiusPill),
                              ),
                              child: const Text('Pending sync',
                                  style: TextStyle(
                                      color: GvColors.medium,
                                      fontSize: 10,
                                      fontWeight: FontWeight.w700)),
                            )
                          else
                            Text(r.status,
                                style: TextStyle(
                                    color: _statusColor(r.status),
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600)),
                        ],
                      ),
                      const SizedBox(height: 6),
                      Text(
                          '${r.siteName} · ${DateFormat.MMMd().format(r.createdAt.toLocal())}',
                          style: const TextStyle(
                              color: GvColors.textMuted, fontSize: 12)),
                      const SizedBox(height: 4),
                      Text(r.description,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: GvColors.textSecondary, fontSize: 13)),
                      if (r.progressPercent > 0) ...[
                        const SizedBox(height: GvSpacing.sm),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: LinearProgressIndicator(
                            value: r.progressPercent / 100,
                            minHeight: 5,
                            backgroundColor: GvColors.surfaceDeep,
                            valueColor:
                                AlwaysStoppedAnimation(_statusColor(r.status)),
                          ),
                        ),
                      ],
                    ],
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }
}
