import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/reports_repository.dart';

class ReportsScreen extends ConsumerWidget {
  const ReportsScreen({super.key});

  IconData _icon(String type) {
    switch (type) {
      case 'ndvi':
        return Icons.eco_outlined;
      case 'thermal':
        return Icons.thermostat;
      case 'inspection':
        return Icons.search;
      default:
        return Icons.description_outlined;
    }
  }

  String _size(int bytes) => '${(bytes / 1_000_000).toStringAsFixed(1)} MB';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(reportsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Reports')),
      body: async.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(message: '$e'),
        data: (reports) => reports.isEmpty
            ? const GvEmpty(message: 'No reports available.')
            : ListView.separated(
                padding: const EdgeInsets.all(GvSpacing.lg),
                itemCount: reports.length,
                separatorBuilder: (_, __) =>
                    const SizedBox(height: GvSpacing.sm),
                itemBuilder: (c, i) {
                  final r = reports[i];
                  return GvCard(
                    onTap: () => showModalBottomSheet<void>(
                      context: context,
                      backgroundColor: GvColors.surface,
                      builder: (_) => _ReportSheet(
                          title: r.title, size: _size(r.sizeBytes)),
                    ),
                    child: Row(
                      children: [
                        Icon(_icon(r.type), color: GvColors.accentCyan),
                        const SizedBox(width: GvSpacing.md),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(r.title,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.w700)),
                              Text(
                                  '${r.siteName} · ${DateFormat.yMMMd().format(r.createdAt.toLocal())} · ${_size(r.sizeBytes)}',
                                  style: const TextStyle(
                                      color: GvColors.textMuted, fontSize: 12)),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right,
                            color: GvColors.textMuted),
                      ],
                    ),
                  );
                },
              ),
      ),
    );
  }
}

class _ReportSheet extends StatelessWidget {
  const _ReportSheet({required this.title, required this.size});
  final String title;
  final String size;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(GvSpacing.xl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title,
              style:
                  const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text('PDF · $size',
              style: const TextStyle(color: GvColors.textMuted)),
          const SizedBox(height: GvSpacing.lg),
          const Text(
              'Secure documents open via a short-lived signed URL. Private storage URLs are never exposed permanently.',
              style: TextStyle(color: GvColors.textSecondary, fontSize: 13)),
          const SizedBox(height: GvSpacing.lg),
          FilledButton.icon(
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('Demo: requesting signed URL…')),
              );
            },
            icon: const Icon(Icons.open_in_new),
            label: const Text('Open securely'),
          ),
          const SizedBox(height: GvSpacing.sm),
          OutlinedButton.icon(
            onPressed: () => Navigator.pop(context),
            icon: const Icon(Icons.download_outlined),
            label: const Text('Download'),
          ),
        ],
      ),
    );
  }
}
