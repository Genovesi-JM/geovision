import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/actions_repository.dart';
import '../domain/customer_action.dart';

class ActionsScreen extends ConsumerStatefulWidget {
  const ActionsScreen({super.key, this.assetId});
  final String? assetId;

  @override
  ConsumerState<ActionsScreen> createState() => _ActionsScreenState();
}

class _ActionsScreenState extends ConsumerState<ActionsScreen> {
  CustomerActionBucket _bucket = CustomerActionBucket.critical;

  @override
  Widget build(BuildContext context) {
    final actions = ref.watch(actionsProvider(widget.assetId));
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.assetId == null ? 'Actions' : 'Asset actions')),
      body: actions.when(
        loading: () => const GvLoading(label: 'Loading actions…'),
        error: (_, __) => GvErrorState(
          message: 'Actions could not be loaded.',
          onRetry: () => ref.invalidate(actionsProvider(widget.assetId)),
        ),
        data: (buckets) => Column(
          children: [
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.all(GvSpacing.md),
              child: SegmentedButton<CustomerActionBucket>(
                showSelectedIcon: false,
                segments: [
                  for (final bucket in CustomerActionBucket.values)
                    ButtonSegment(
                      value: bucket,
                      label: Text(
                          '${bucket.label} (${buckets.items(bucket).length})'),
                    ),
                ],
                selected: {_bucket},
                onSelectionChanged: (selected) =>
                    setState(() => _bucket = selected.first),
              ),
            ),
            Expanded(
              child: _ActionList(
                items: buckets.items(_bucket),
                onRefresh: () async {
                  ref.invalidate(actionsProvider(widget.assetId));
                  await ref.read(actionsProvider(widget.assetId).future);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionList extends StatelessWidget {
  const _ActionList({required this.items, required this.onRefresh});
  final List<CustomerAction> items;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: const [
            SizedBox(
              height: 360,
              child: GvEmpty(
                message: 'No actions in this group.',
                icon: Icons.task_alt,
              ),
            ),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: onRefresh,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.fromLTRB(
            GvSpacing.lg, 0, GvSpacing.lg, GvSpacing.lg),
        itemCount: items.length,
        separatorBuilder: (_, __) => const SizedBox(height: GvSpacing.sm),
        itemBuilder: (context, index) {
          final item = items[index];
          return GvCard(
            onTap: () => context.push('/actions/${item.id}'),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(_priorityIcon(item.priority),
                  color: _priorityColor(item.priority)),
              const SizedBox(width: GvSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 3),
                    Text(item.description,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: GvColors.textSecondary, fontSize: 12)),
                    if (item.dueDate case final due?)
                      Text(DateFormat.MMMd().add_Hm().format(due.toLocal()),
                          style: const TextStyle(
                              color: GvColors.textMuted, fontSize: 11)),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: GvColors.textMuted),
            ]),
          );
        },
      ),
    );
  }
}

Color _priorityColor(String priority) => switch (priority) {
      'CRITICAL' => GvColors.critical,
      'URGENT' || 'HIGH' => GvColors.high,
      'MEDIUM' => GvColors.medium,
      _ => GvColors.accentCyan,
    };

IconData _priorityIcon(String priority) =>
    priority == 'CRITICAL' || priority == 'URGENT'
        ? Icons.priority_high
        : Icons.task_alt_outlined;
