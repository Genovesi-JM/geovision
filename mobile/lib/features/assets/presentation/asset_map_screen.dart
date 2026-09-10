import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/assets_repository.dart';

class AssetMapScreen extends ConsumerWidget {
  const AssetMapScreen({super.key, required this.assetId});

  final String assetId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final asset = ref.watch(customerAssetDetailProvider(assetId));
    return Scaffold(
      appBar: AppBar(title: const Text('Asset map')),
      body: asset.when(
        loading: () => const GvLoading(label: 'Loading asset map…'),
        error: (_, __) => GvErrorState(
          message: 'The asset map could not be loaded.',
          onRetry: () => ref.invalidate(customerAssetDetailProvider(assetId)),
        ),
        data: (item) {
          if (item == null) {
            return const GvEmpty(message: 'Asset not found.');
          }
          if (!item.hasLocation) {
            return const GvEmpty(
              message: 'This asset does not have a map location yet.',
              icon: Icons.location_off_outlined,
            );
          }
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              Semantics(
                image: true,
                label:
                    'Map position for ${item.name}, latitude ${item.latitude}, longitude ${item.longitude}',
                child: Container(
                  height: 360,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(GvSpacing.radiusLg),
                    border: Border.all(color: GvColors.border),
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [Color(0xFF092337), Color(0xFF071A20)],
                    ),
                  ),
                  child: const Center(
                    child: Icon(
                      Icons.location_on,
                      size: 58,
                      color: GvColors.accentCyan,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: GvSpacing.md),
              GvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.name,
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    if (item.locationLabel.isNotEmpty)
                      Text(
                        item.locationLabel,
                        style: const TextStyle(color: GvColors.textSecondary),
                      ),
                    Text(
                      '${item.latitude!.toStringAsFixed(5)}, ${item.longitude!.toStringAsFixed(5)}',
                      style: const TextStyle(color: GvColors.textMuted),
                    ),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
