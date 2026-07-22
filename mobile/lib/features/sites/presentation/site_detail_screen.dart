import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_section_header.dart';
import '../../../core/widgets/gv_states.dart';
import '../../../core/widgets/kpi_card.dart';
import '../data/sites_repository.dart';
import '../domain/sector.dart';

class SiteDetailScreen extends ConsumerWidget {
  const SiteDetailScreen({super.key, required this.siteId});
  final String siteId;

  KpiTrend _trend(String t) =>
      t == 'up' ? KpiTrend.up : (t == 'down' ? KpiTrend.down : KpiTrend.stable);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final siteAsync = ref.watch(siteDetailProvider(siteId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Site detail'),
        actions: [
          IconButton(
            tooltip: 'Perguntar à GAIA sobre este local',
            icon: const Icon(Icons.auto_awesome),
            onPressed: () => context.go('/assistant?from=site&site=$siteId'),
          ),
          IconButton(
            icon: const Icon(Icons.map_outlined),
            onPressed: () => context.go('/sites/$siteId/map'),
          ),
        ],
      ),
      body: siteAsync.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(message: '$e'),
        data: (site) {
          if (site == null) return const GvEmpty(message: 'Site not found.');
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              GvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(site.name,
                        style: const TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text('${site.location} · ${site.sector.label}',
                        style: const TextStyle(color: GvColors.textSecondary)),
                    const SizedBox(height: GvSpacing.md),
                    Row(
                      children: [
                        _Stat(
                            label: 'Area',
                            value:
                                '${site.totalHectares.toStringAsFixed(0)} ha'),
                        _Stat(label: 'Fields', value: '${site.areas.length}'),
                        _Stat(
                            label: 'Open alerts', value: '${site.openAlerts}'),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: GvSpacing.md),
              const GvSectionHeader(title: 'KPI summary'),
              GridView.count(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                crossAxisCount: 2,
                mainAxisSpacing: GvSpacing.sm,
                crossAxisSpacing: GvSpacing.sm,
                childAspectRatio: 1.45,
                children: site.kpis
                    .map((k) => KpiCard(
                          label: k.label,
                          value: k.value.toString(),
                          unit: k.unit,
                          status: kpiStatusFromString(k.status),
                          trend: _trend(k.trend),
                          spark: k.spark,
                        ))
                    .toList(),
              ),
              const SizedBox(height: GvSpacing.md),
              const GvSectionHeader(title: 'Fields'),
              ...site.areas.map((a) => Padding(
                    padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                    child: GvCard(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.grass,
                                  color: GvColors.accentGreen, size: 18),
                              const SizedBox(width: GvSpacing.sm),
                              Expanded(
                                child: Text(a.name,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w700)),
                              ),
                              Text(
                                  '${a.hectares.toStringAsFixed(0)} ha · ${a.crop}',
                                  style: const TextStyle(
                                      color: GvColors.textMuted, fontSize: 12)),
                            ],
                          ),
                          if (a.kpis.isNotEmpty) ...[
                            const SizedBox(height: GvSpacing.sm),
                            Wrap(
                              spacing: GvSpacing.sm,
                              runSpacing: 4,
                              children: a.kpis
                                  .map((k) => _MiniKpi(
                                      label: k.label,
                                      value: '${k.value}${k.unit ?? ''}',
                                      status: k.status))
                                  .toList(),
                            ),
                          ],
                        ],
                      ),
                    ),
                  )),
              const SizedBox(height: GvSpacing.xxl),
            ],
          );
        },
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value,
                style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                    color: GvColors.textPrimary)),
            Text(label,
                style:
                    const TextStyle(color: GvColors.textMuted, fontSize: 11)),
          ],
        ),
      );
}

class _MiniKpi extends StatelessWidget {
  const _MiniKpi(
      {required this.label, required this.value, required this.status});
  final String label;
  final String value;
  final String status;
  @override
  Widget build(BuildContext context) {
    final c = status == 'critical'
        ? GvColors.critical
        : status == 'warning'
            ? GvColors.medium
            : GvColors.accentGreen;
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: GvSpacing.sm, vertical: 4),
      decoration: BoxDecoration(
        color: GvColors.surfaceDeep,
        borderRadius: BorderRadius.circular(GvSpacing.radiusSm),
        border: Border.all(color: GvColors.border),
      ),
      child: Text('$label $value',
          style:
              TextStyle(color: c, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}
