import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/notifications_repository.dart';

class NotificationContextScreen extends ConsumerWidget {
  const NotificationContextScreen({
    required this.targetType,
    required this.targetId,
    super.key,
  });

  final String targetType;
  final String targetId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = (type: targetType.toUpperCase(), id: targetId);
    final details = ref.watch(notificationContextProvider(key));
    return Scaffold(
      appBar: AppBar(title: Text(_title(targetType))),
      body: details.when(
        loading: () => const GvLoading(label: 'Loading details…'),
        error: (error, _) => GvErrorState(
          message: '$error',
          onRetry: () => ref.invalidate(notificationContextProvider(key)),
        ),
        data: (item) => ListView(
          padding: const EdgeInsets.all(GvSpacing.lg),
          children: [
            GvCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(_icon(item.type),
                          color: GvColors.accentCyan, size: 28),
                      const SizedBox(width: GvSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(item.title,
                                style: const TextStyle(
                                    fontSize: 19, fontWeight: FontWeight.w800)),
                            const SizedBox(height: 4),
                            Text(item.status,
                                style: const TextStyle(
                                    color: GvColors.accentGreen,
                                    fontWeight: FontWeight.w700)),
                          ],
                        ),
                      ),
                    ],
                  ),
                  if (item.description != null &&
                      item.description!.isNotEmpty) ...[
                    const SizedBox(height: GvSpacing.md),
                    Text(item.description!,
                        style: const TextStyle(
                            color: GvColors.textSecondary, height: 1.45)),
                  ],
                ],
              ),
            ),
            if (item.facts.isNotEmpty) ...[
              const SizedBox(height: GvSpacing.md),
              GvCard(
                child: Column(
                  children: [
                    for (final fact in item.facts.entries)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 7),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(fact.key,
                                  style: const TextStyle(
                                      color: GvColors.textMuted)),
                            ),
                            const SizedBox(width: GvSpacing.md),
                            Expanded(
                              child: Text(fact.value,
                                  textAlign: TextAlign.end,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w600)),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: GvSpacing.md),
            OutlinedButton.icon(
              onPressed: () => context.go(_collectionPath(item.type)),
              icon: const Icon(Icons.arrow_back),
              label: Text(_collectionLabel(item.type)),
            ),
            const SizedBox(height: GvSpacing.md),
            Text(
              'Reference: ${item.id}',
              textAlign: TextAlign.center,
              style: const TextStyle(color: GvColors.textMuted, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }

  static String _title(String type) => switch (type.toUpperCase()) {
        'ASSET' => 'Asset details',
        'REPORT' => 'Report details',
        'ACTION' => 'Action details',
        'SERVICE' => 'Service details',
        _ => 'Details',
      };

  static IconData _icon(String type) => switch (type) {
        'ASSET' => Icons.terrain_outlined,
        'REPORT' => Icons.description_outlined,
        'ACTION' => Icons.task_alt,
        'SERVICE' => Icons.home_repair_service_outlined,
        _ => Icons.info_outline,
      };

  static String _collectionPath(String type) => switch (type) {
        'ASSET' => '/sites',
        'REPORT' => '/reports',
        'ACTION' || 'SERVICE' => '/work',
        _ => '/portal',
      };

  static String _collectionLabel(String type) => switch (type) {
        'ASSET' => 'All assets',
        'REPORT' => 'All reports',
        'ACTION' => 'All work',
        'SERVICE' => 'All services',
        _ => 'Back to portal',
      };
}
