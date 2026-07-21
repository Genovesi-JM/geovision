import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_section_header.dart';
import '../../../core/widgets/gv_states.dart';
import '../../../core/widgets/kpi_card.dart';
import '../../../core/widgets/quick_action.dart';
import '../../../core/widgets/severity_chip.dart';
import '../data/home_repository.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(homeSummaryProvider);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(homeSummaryProvider.future),
        child: summary.when(
          loading: () => const GvLoading(label: 'Loading operational summary…'),
          error: (e, _) => GvErrorState(
              message: '$e', onRetry: () => ref.refresh(homeSummaryProvider)),
          data: (s) => ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(s.organisation,
                            style: const TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.w800,
                                color: GvColors.textPrimary)),
                        if (s.selectedSite != null)
                          Text(s.selectedSite!.name,
                              style: const TextStyle(
                                  color: GvColors.accentCyan, fontSize: 13)),
                      ],
                    ),
                  ),
                  if (s.lastSyncedAt != null)
                    Text(DateFormat.Hm().format(s.lastSyncedAt!.toLocal()),
                        style: const TextStyle(
                            color: GvColors.textMuted, fontSize: 11)),
                ],
              ),
              const SizedBox(height: GvSpacing.lg),
              const GvSectionHeader(title: 'Quick actions'),
              GridView.count(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisCount: 4,
                mainAxisSpacing: GvSpacing.sm,
                crossAxisSpacing: GvSpacing.sm,
                childAspectRatio: 0.82,
                children: [
                  QuickAction(
                      icon: Icons.map_outlined,
                      label: 'Site map',
                      onTap: () {
                        final id = s.selectedSite?.id;
                        if (id != null) context.go('/sites/$id/map');
                      }),
                  QuickAction(
                      icon: Icons.add_task,
                      label: 'Request',
                      onTap: () => context.go('/work/new')),
                  QuickAction(
                      icon: Icons.description_outlined,
                      label: 'Reports',
                      onTap: () => context.go('/reports')),
                  QuickAction(
                      icon: Icons.warning_amber,
                      label: 'Alerts',
                      onTap: () => context.go('/alerts')),
                ],
              ),
              const SizedBox(height: GvSpacing.md),
              GvSectionHeader(
                title: 'Critical alerts',
                action: TextButton(
                    onPressed: () => context.go('/alerts'),
                    child: const Text('View all')),
              ),
              if (s.criticalAlerts.isEmpty)
                const GvCard(
                    child: Text(
                        'No critical alerts. All monitored sites nominal.',
                        style: TextStyle(color: GvColors.textSecondary)))
              else
                ...s.criticalAlerts.take(3).map((a) => Padding(
                      padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                      child: GvCard(
                        onTap: () => context.go('/alerts/${a.id}'),
                        child: Row(
                          children: [
                            SeverityChip(severityFromString(a.severity)),
                            const SizedBox(width: GvSpacing.md),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(a.title,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w700)),
                                  Text(a.location ?? '',
                                      style: const TextStyle(
                                          color: GvColors.textMuted,
                                          fontSize: 12)),
                                ],
                              ),
                            ),
                            const Icon(Icons.chevron_right,
                                color: GvColors.textMuted),
                          ],
                        ),
                      ),
                    )),
              const SizedBox(height: GvSpacing.md),
              if (s.selectedSite != null &&
                  s.selectedSite!.kpis.isNotEmpty) ...[
                GvSectionHeader(
                  title: 'KPI summary',
                  action: TextButton(
                      onPressed: () =>
                          context.go('/sites/${s.selectedSite!.id}'),
                      child: const Text('Site detail')),
                ),
                GridView.count(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisCount: 2,
                  mainAxisSpacing: GvSpacing.sm,
                  crossAxisSpacing: GvSpacing.sm,
                  childAspectRatio: 1.5,
                  children: s.selectedSite!.kpis
                      .take(4)
                      .map((k) => KpiCard(
                            label: k.label,
                            value: k.value.toString(),
                            unit: k.unit,
                            status: kpiStatusFromString(k.status),
                            trend: k.trend == 'up'
                                ? KpiTrend.up
                                : k.trend == 'down'
                                    ? KpiTrend.down
                                    : KpiTrend.stable,
                            spark: k.spark,
                          ))
                      .toList(),
                ),
                const SizedBox(height: GvSpacing.md),
              ],
              const GvSectionHeader(title: 'Active operations'),
              if (s.activeRequests.isEmpty)
                const GvCard(
                    child: Text('No active operations.',
                        style: TextStyle(color: GvColors.textSecondary)))
              else
                ...s.activeRequests.take(3).map((r) => Padding(
                      padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                      child: GvCard(
                        child: Row(
                          children: [
                            const Icon(Icons.flight_takeoff,
                                color: GvColors.accentSky, size: 20),
                            const SizedBox(width: GvSpacing.md),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('${r.siteName} · ${r.status}',
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w600)),
                                  if (r.pendingSync)
                                    const Text('Pending sync',
                                        style: TextStyle(
                                            color: GvColors.medium,
                                            fontSize: 11)),
                                ],
                              ),
                            ),
                            Text('${r.progressPercent}%',
                                style: const TextStyle(
                                    color: GvColors.accentGreen)),
                          ],
                        ),
                      ),
                    )),
              const SizedBox(height: GvSpacing.md),
              GvSectionHeader(
                title: 'Device health',
                action: Text('${s.onlineDevices}/${s.totalDevices} online',
                    style: const TextStyle(
                        color: GvColors.accentGreen, fontSize: 12)),
              ),
              if (s.latestReport != null)
                GvCard(
                  onTap: () => context.go('/reports'),
                  child: Row(
                    children: [
                      const Icon(Icons.picture_as_pdf_outlined,
                          color: GvColors.accentCyan),
                      const SizedBox(width: GvSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Latest report',
                                style: TextStyle(
                                    color: GvColors.textMuted, fontSize: 11)),
                            Text(s.latestReport!.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600)),
                          ],
                        ),
                      ),
                      const Icon(Icons.chevron_right,
                          color: GvColors.textMuted),
                    ],
                  ),
                ),
              const SizedBox(height: GvSpacing.xxl),
            ],
          ),
        ),
      ),
    );
  }
}
