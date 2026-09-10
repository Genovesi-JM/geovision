import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/work_repository.dart';

class ServiceRequestDetailScreen extends ConsumerWidget {
  const ServiceRequestDetailScreen({super.key, required this.requestId});
  final String requestId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final request = ref.watch(serviceRequestDetailProvider(requestId));
    return Scaffold(
      appBar: AppBar(title: const Text('Service result')),
      body: request.when(
        loading: () => const GvLoading(label: 'Loading service result…'),
        error: (_, __) => GvErrorState(
          message: 'This service result could not be loaded.',
          onRetry: () =>
              ref.invalidate(serviceRequestDetailProvider(requestId)),
        ),
        data: (item) {
          if (item == null) {
            return const GvEmpty(
              message: 'Service result not found.',
              icon: Icons.fact_check_outlined,
            );
          }
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              GvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.resultTitle ?? item.siteName,
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.w800)),
                    const SizedBox(height: GvSpacing.xs),
                    Text(item.resultSummary ?? item.description,
                        style: const TextStyle(
                            color: GvColors.textSecondary, height: 1.4)),
                    const SizedBox(height: GvSpacing.md),
                    LinearProgressIndicator(
                        value: item.progressPercent.clamp(0, 100) / 100),
                    const SizedBox(height: GvSpacing.sm),
                    Text(
                      '${item.status.replaceAll('_', ' ')} · ${DateFormat.yMMMd().format(item.createdAt.toLocal())}',
                      style: const TextStyle(
                          color: GvColors.textMuted, fontSize: 12),
                    ),
                    if (item.assignedTeam case final team?)
                      Text('GeoVision team: $team',
                          style: const TextStyle(
                              color: GvColors.accentCyan, fontSize: 12)),
                  ],
                ),
              ),
              if (item.attachments.isNotEmpty) ...[
                const SizedBox(height: GvSpacing.md),
                const Text('Delivered files',
                    style:
                        TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                const SizedBox(height: GvSpacing.sm),
                for (final attachment in item.attachments)
                  ListTile(
                    leading: const Icon(Icons.attach_file),
                    title: Text(attachment),
                  ),
              ],
              if (item.resultReportId case final reportId?) ...[
                const SizedBox(height: GvSpacing.md),
                FilledButton.icon(
                  onPressed: () => context.push('/reports/$reportId'),
                  icon: const Icon(Icons.description_outlined),
                  label: const Text('Open published report'),
                ),
              ],
              if (item.resultAssetId case final assetId?) ...[
                const SizedBox(height: GvSpacing.sm),
                OutlinedButton.icon(
                  onPressed: () => context.push('/assets/$assetId'),
                  icon: const Icon(Icons.landscape_outlined),
                  label: const Text('Open existing asset'),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
