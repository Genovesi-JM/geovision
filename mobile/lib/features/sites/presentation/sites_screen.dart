import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/sites_repository.dart';
import '../domain/sector.dart';
import '../domain/site.dart';

final _queryProvider = StateProvider<String>((ref) => '');
final _sectorFilterProvider = StateProvider<Sector?>((ref) => null);

class SitesScreen extends ConsumerWidget {
  const SitesScreen({super.key});

  Color _statusColor(SiteStatus s) {
    switch (s) {
      case SiteStatus.active:
        return GvColors.accentGreen;
      case SiteStatus.attention:
        return GvColors.medium;
      case SiteStatus.offline:
        return GvColors.textMuted;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sitesAsync = ref.watch(sitesProvider);
    final query = ref.watch(_queryProvider).toLowerCase();
    final sectorFilter = ref.watch(_sectorFilterProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Locais'),
        actions: [
          IconButton(
            tooltip: 'Adicionar local',
            onPressed: () => context.go('/sites/new'),
            icon: const Icon(Icons.add_location_alt_outlined),
          ),
          const SizedBox(width: GvSpacing.sm),
        ],
      ),
      body: sitesAsync.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(
            message: '$e', onRetry: () => ref.refresh(sitesProvider)),
        data: (env) {
          final sites = env.value.where((s) {
            final matchesQuery = query.isEmpty ||
                s.name.toLowerCase().contains(query) ||
                s.location.toLowerCase().contains(query);
            final matchesSector =
                sectorFilter == null || s.sector == sectorFilter;
            return matchesQuery && matchesSector;
          }).toList();

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(GvSpacing.lg),
                child: TextField(
                  onChanged: (v) => ref.read(_queryProvider.notifier).state = v,
                  decoration: const InputDecoration(
                      hintText: 'Search sites', prefixIcon: Icon(Icons.search)),
                ),
              ),
              SizedBox(
                height: 40,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: GvSpacing.lg),
                  children: [
                    _FilterChip(
                      label: 'All',
                      selected: sectorFilter == null,
                      onTap: () =>
                          ref.read(_sectorFilterProvider.notifier).state = null,
                    ),
                    for (final sec in Sector.values)
                      _FilterChip(
                        label: sec.label,
                        selected: sectorFilter == sec,
                        onTap: () => ref
                            .read(_sectorFilterProvider.notifier)
                            .state = sec,
                      ),
                  ],
                ),
              ),
              const SizedBox(height: GvSpacing.sm),
              Expanded(
                child: sites.isEmpty
                    ? const GvEmpty(message: 'No sites match your filters.')
                    : ListView.separated(
                        padding: const EdgeInsets.all(GvSpacing.lg),
                        itemCount: sites.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: GvSpacing.sm),
                        itemBuilder: (c, i) {
                          final s = sites[i];
                          return GvCard(
                            onTap: () => context.go('/sites/${s.id}'),
                            child: Row(
                              children: [
                                Container(
                                  width: 10,
                                  height: 10,
                                  decoration: BoxDecoration(
                                      color: _statusColor(s.status),
                                      shape: BoxShape.circle),
                                ),
                                const SizedBox(width: GvSpacing.md),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(s.name,
                                          style: const TextStyle(
                                              fontWeight: FontWeight.w700,
                                              fontSize: 15)),
                                      Text('${s.location} · ${s.sector.label}',
                                          style: const TextStyle(
                                              color: GvColors.textMuted,
                                              fontSize: 12)),
                                    ],
                                  ),
                                ),
                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text(
                                        '${s.totalHectares.toStringAsFixed(0)} ha',
                                        style: const TextStyle(
                                            color: GvColors.textSecondary,
                                            fontSize: 12)),
                                    if (s.openAlerts > 0)
                                      Text('${s.openAlerts} alerts',
                                          style: const TextStyle(
                                              color: GvColors.high,
                                              fontSize: 12)),
                                  ],
                                ),
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

class _FilterChip extends StatelessWidget {
  const _FilterChip(
      {required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: GvSpacing.sm),
      child: ChoiceChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) => onTap(),
        selectedColor: GvColors.accentCyan.withValues(alpha: 0.2),
        labelStyle: TextStyle(
            color: selected ? GvColors.accentCyan : GvColors.textSecondary,
            fontSize: 12),
        backgroundColor: GvColors.surfaceDeep,
        side: const BorderSide(color: GvColors.border),
      ),
    );
  }
}
