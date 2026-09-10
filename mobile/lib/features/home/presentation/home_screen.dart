import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_section_header.dart';
import '../../../core/widgets/gv_states.dart';
import '../../account/data/customer_experience_repository.dart';
import '../data/home_repository.dart';
import '../domain/home_summary.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final summary = ref.watch(homeSummaryProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Home'),
        actions: [
          IconButton(
            tooltip: 'Notifications',
            onPressed: () => context.push('/notifications'),
            icon: const Icon(Icons.notifications_outlined),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.refresh(homeSummaryProvider.future),
        child: summary.when(
          loading: () =>
              const GvLoading(label: 'Loading what needs attention…'),
          error: (_, __) => GvErrorState(
            message: 'Your operational summary could not be loaded.',
            onRetry: () => ref.invalidate(homeSummaryProvider),
          ),
          data: (data) => _HomeContent(data: data),
        ),
      ),
    );
  }
}

/// Compatibility name retained for callers compiled against the old portal.
class PortalScreen extends HomeScreen {
  const PortalScreen({super.key});
}

class _HomeContent extends ConsumerWidget {
  const _HomeContent({required this.data});
  final HomeSummary data;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final capabilities = ref.watch(customerExperienceProvider).valueOrNull;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(GvSpacing.lg),
      children: [
        Text(data.organizationName,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        if (data.workspaceName.isNotEmpty)
          Text(data.workspaceName,
              style: const TextStyle(color: GvColors.accentCyan)),
        const SizedBox(height: GvSpacing.lg),
        Semantics(
          container: true,
          label:
              '${data.attention.needsAttention} items need attention. ${data.attention.scheduled} scheduled.',
          child: GvCard(
            child: Row(children: [
              _AttentionCount(
                  value: data.attention.critical,
                  label: 'Critical',
                  color: GvColors.critical),
              _AttentionCount(
                  value: data.attention.attention,
                  label: 'Attention',
                  color: GvColors.high),
              _AttentionCount(
                  value: data.attention.scheduled,
                  label: 'Scheduled',
                  color: GvColors.medium),
            ]),
          ),
        ),
        const SizedBox(height: GvSpacing.lg),
        const GvSectionHeader(title: 'What needs your attention now?'),
        if (data.priorityItems.isEmpty)
          const GvEmpty(
            message: 'Nothing needs your attention right now.',
            icon: Icons.task_alt,
          )
        else
          ...data.priorityItems.map((item) => Padding(
                padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                child: _PriorityCard(item: item),
              )),
        if (data.latestResult case final result?) ...[
          const SizedBox(height: GvSpacing.md),
          const GvSectionHeader(title: 'Latest result'),
          GvCard(
            onTap: result.appPath == null
                ? null
                : () => context.push(result.appPath!),
            child: Row(children: [
              const Icon(Icons.fact_check_outlined,
                  color: GvColors.accentGreen),
              const SizedBox(width: GvSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(result.title,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    Text(result.summary,
                        style: const TextStyle(
                            color: GvColors.textSecondary, fontSize: 12)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: GvColors.textMuted),
            ]),
          ),
        ],
        const SizedBox(height: GvSpacing.lg),
        const GvSectionHeader(title: 'Continue'),
        Wrap(
          spacing: GvSpacing.sm,
          runSpacing: GvSpacing.sm,
          children: [
            if (capabilities?.hasCapability('assets') == true)
              ActionChip(
                avatar: const Icon(Icons.landscape_outlined, size: 18),
                label: const Text('Assets'),
                onPressed: () => context.go('/assets'),
              ),
            if (capabilities?.hasCapability('actions') == true)
              ActionChip(
                avatar: const Icon(Icons.task_alt_outlined, size: 18),
                label: const Text('Actions'),
                onPressed: () => context.go('/actions'),
              ),
            if (capabilities?.hasCapability('services') == true)
              ActionChip(
                avatar: const Icon(Icons.design_services_outlined, size: 18),
                label: const Text('Services'),
                onPressed: () => context.go('/services'),
              ),
          ],
        ),
        const SizedBox(height: GvSpacing.lg),
        Text(
          'Updated ${DateFormat.Hm().format(data.updatedAt.toLocal())}',
          textAlign: TextAlign.center,
          style: const TextStyle(color: GvColors.textMuted, fontSize: 11),
        ),
      ],
    );
  }
}

class _AttentionCount extends StatelessWidget {
  const _AttentionCount(
      {required this.value, required this.label, required this.color});
  final int value;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Expanded(
        child: Column(children: [
          Text('$value',
              style: TextStyle(
                  color: color, fontSize: 24, fontWeight: FontWeight.w800)),
          Text(label,
              style:
                  const TextStyle(color: GvColors.textSecondary, fontSize: 11)),
        ]),
      );
}

class _PriorityCard extends StatelessWidget {
  const _PriorityCard({required this.item});
  final HomePriorityItem item;

  Color get _color => switch (item.severity) {
        'critical' => GvColors.critical,
        'scheduled' => GvColors.medium,
        _ => GvColors.high,
      };

  @override
  Widget build(BuildContext context) => GvCard(
        onTap: item.appPath == null ? null : () => context.push(item.appPath!),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 10,
            height: 10,
            margin: const EdgeInsets.only(top: 5),
            decoration: BoxDecoration(color: _color, shape: BoxShape.circle),
          ),
          const SizedBox(width: GvSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.title,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 3),
                Text(item.summary,
                    style: const TextStyle(
                        color: GvColors.textSecondary, fontSize: 12)),
                if (item.dueAt case final due?)
                  Text(
                      'Due ${DateFormat.MMMd().add_Hm().format(due.toLocal())}',
                      style: const TextStyle(
                          color: GvColors.textMuted, fontSize: 11)),
              ],
            ),
          ),
          const Icon(Icons.chevron_right, color: GvColors.textMuted),
        ]),
      );
}
