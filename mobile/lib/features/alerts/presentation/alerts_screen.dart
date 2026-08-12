import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../../../core/widgets/severity_chip.dart';
import '../data/alerts_repository.dart';
import '../../../l10n/app_localizations.dart';
import 'alert_copy.dart';

final _showResolvedProvider = StateProvider<bool>((ref) => false);
final _severityFilterProvider = StateProvider<String?>((ref) => null);

class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final text = AppLocalizations.of(context);
    final copy = AlertCopy.of(context);
    final alertsAsync = ref.watch(alertsProvider);
    final showResolved = ref.watch(_showResolvedProvider);
    final sevFilter = ref.watch(_severityFilterProvider);

    return Scaffold(
      appBar: AppBar(
        title: Text(text.navAlerts),
        actions: [
          IconButton(
            icon: Icon(showResolved ? Icons.visibility : Icons.visibility_off),
            tooltip: showResolved ? text.hideResolved : text.showResolved,
            onPressed: () =>
                ref.read(_showResolvedProvider.notifier).state = !showResolved,
          ),
        ],
      ),
      body: alertsAsync.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(
            message: '$e', onRetry: () => ref.refresh(alertsProvider)),
        data: (env) {
          final alerts = env.value.where((a) {
            if (!showResolved && a.resolved) return false;
            if (sevFilter != null && a.severity != sevFilter) return false;
            return true;
          }).toList();

          return Column(
            children: [
              SizedBox(
                height: 44,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(
                      horizontal: GvSpacing.lg, vertical: 4),
                  children: [
                    for (final s in [
                      'critical',
                      'high',
                      'medium',
                      'low',
                      'information'
                    ])
                      Padding(
                        padding: const EdgeInsets.only(right: GvSpacing.sm),
                        child: FilterChip(
                          label: Text(
                              severityFromString(s).localizedLabel(context),
                              style: const TextStyle(fontSize: 11)),
                          selected: sevFilter == s,
                          onSelected: (v) => ref
                              .read(_severityFilterProvider.notifier)
                              .state = v ? s : null,
                          backgroundColor: GvColors.surfaceDeep,
                          selectedColor: severityFromString(s)
                              .color
                              .withValues(alpha: 0.2),
                          side: const BorderSide(color: GvColors.border),
                        ),
                      ),
                  ],
                ),
              ),
              Expanded(
                child: alerts.isEmpty
                    ? GvEmpty(
                        message: text.noAlertsMatch,
                        icon: Icons.notifications_none)
                    : ListView.separated(
                        padding: const EdgeInsets.all(GvSpacing.lg),
                        itemCount: alerts.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: GvSpacing.sm),
                        itemBuilder: (c, i) {
                          final a = alerts[i];
                          return GvCard(
                            onTap: () => context.go('/alerts/${a.id}'),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    SeverityChip(
                                        severityFromString(a.severity)),
                                    const Spacer(),
                                    if (a.acknowledged)
                                      const Icon(Icons.check_circle,
                                          size: 16,
                                          color: GvColors.accentGreen),
                                    const SizedBox(width: 4),
                                    Text(
                                        DateFormat.MMMd()
                                            .add_Hm()
                                            .format(a.createdAt.toLocal()),
                                        style: const TextStyle(
                                            color: GvColors.textMuted,
                                            fontSize: 11)),
                                  ],
                                ),
                                const SizedBox(height: GvSpacing.sm),
                                Text(copy.title(a),
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 15)),
                                const SizedBox(height: 2),
                                Text(copy.description(a),
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(
                                        color: GvColors.textSecondary,
                                        fontSize: 13)),
                                if (a.location != null) ...[
                                  const SizedBox(height: 6),
                                  Row(children: [
                                    const Icon(Icons.place_outlined,
                                        size: 14, color: GvColors.textMuted),
                                    const SizedBox(width: 4),
                                    Text(a.location!,
                                        style: const TextStyle(
                                            color: GvColors.textMuted,
                                            fontSize: 12)),
                                  ]),
                                ],
                              ],
                            ),
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}
