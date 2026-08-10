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
import '../../../l10n/app_localizations.dart';
import '../../sites/presentation/kpi_labels.dart';
import '../data/home_repository.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(homeSummaryProvider);
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(homeSummaryProvider.future),
        child: summary.when(
          loading: () => GvLoading(label: l10n.loadingSummary),
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
              GvSectionHeader(title: l10n.quickActions),
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
                      label: l10n.siteMap,
                      onTap: () {
                        final id = s.selectedSite?.id;
                        if (id != null) context.go('/sites/$id/map');
                      }),
                  QuickAction(
                      icon: Icons.terrain_outlined,
                      label: l10n.navAssets,
                      onTap: () => context.go('/sites')),
                  QuickAction(
                      icon: Icons.sensors_outlined,
                      label: l10n.devices,
                      onTap: () => context.go('/devices')),
                  QuickAction(
                      icon: Icons.warning_amber,
                      label: l10n.navAlerts,
                      onTap: () => context.go('/alerts')),
                ],
              ),
              const SizedBox(height: GvSpacing.md),
              GvSectionHeader(
                title: l10n.criticalAlerts,
                action: TextButton(
                    onPressed: () => context.go('/alerts'),
                    child: Text(l10n.viewAll)),
              ),
              if (s.criticalAlerts.isEmpty)
                GvCard(
                    child: Text(l10n.noCriticalAlerts,
                        style: const TextStyle(color: GvColors.textSecondary)))
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
                  title: l10n.kpiSummary,
                  action: TextButton(
                      onPressed: () =>
                          context.go('/sites/${s.selectedSite!.id}'),
                      child: Text(l10n.siteDetail)),
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
                            label: localizedKpiLabel(
                                l10n, k.definitionId, k.label),
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
              GvSectionHeader(title: l10n.activeOperations),
              if (s.activeRequests.isEmpty)
                GvCard(
                    child: Text(l10n.noActiveOperations,
                        style: const TextStyle(color: GvColors.textSecondary)))
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
                                    Text(l10n.pendingSync,
                                        style: const TextStyle(
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
                title: l10n.deviceHealth,
                action: Text(
                    '${s.onlineDevices}/${s.totalDevices} ${l10n.deviceOnline.toLowerCase()}',
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
                            Text(l10n.latestReport,
                                style: const TextStyle(
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
