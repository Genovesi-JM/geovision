import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/actions_repository.dart';

class ActionDetailScreen extends ConsumerWidget {
  const ActionDetailScreen({super.key, required this.actionId});
  final String actionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final action = ref.watch(actionDetailProvider(actionId));
    return Scaffold(
      appBar: AppBar(title: const Text('Action detail')),
      body: action.when(
        loading: () => const GvLoading(label: 'Loading action…'),
        error: (_, __) => GvErrorState(
          message: 'This action could not be loaded.',
          onRetry: () => ref.invalidate(actionDetailProvider(actionId)),
        ),
        data: (item) {
          if (item == null) {
            return const GvEmpty(
                message: 'Action not found.', icon: Icons.task_alt);
          }
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              GvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.title,
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w800)),
                    const SizedBox(height: GvSpacing.sm),
                    Text(item.description,
                        style: const TextStyle(
                            color: GvColors.textSecondary, height: 1.4)),
                    const SizedBox(height: GvSpacing.md),
                    Wrap(spacing: 8, children: [
                      Chip(label: Text(item.priority)),
                      Chip(label: Text(item.status.replaceAll('_', ' '))),
                    ]),
                    if (item.dueDate case final due?)
                      Text('Due ${DateFormat.yMMMd().add_Hm().format(due)}'),
                  ],
                ),
              ),
              const SizedBox(height: GvSpacing.md),
              FilledButton.icon(
                onPressed: () => context.push('/assets/${item.assetId}'),
                icon: const Icon(Icons.landscape_outlined),
                label: const Text('Open asset'),
              ),
              if (item.recommendedCatalogItemId case final serviceId?) ...[
                const SizedBox(height: GvSpacing.sm),
                OutlinedButton.icon(
                  onPressed: () => context.push('/services/$serviceId'),
                  icon: const Icon(Icons.design_services_outlined),
                  label: const Text('View recommended GeoVision service'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
