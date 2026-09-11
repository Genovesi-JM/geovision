import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../../app/providers.dart';
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
    final mapProvider = ref.watch(mapProviderProvider);
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
          final tileUrl = mapProvider.tileUrlTemplate();
          final position = LatLng(item.latitude!, item.longitude!);
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              Semantics(
                image: true,
                label:
                    'Map position for ${item.name}, latitude ${item.latitude}, longitude ${item.longitude}',
                child: Container(
                  height: 360,
                  clipBehavior: Clip.antiAlias,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(GvSpacing.radiusLg),
                    border: Border.all(color: GvColors.border),
                  ),
                  child: tileUrl == null
                      ? const _DemoMapSurface()
                      : FlutterMap(
                          options: MapOptions(
                            initialCenter: position,
                            initialZoom: 15,
                            maxZoom: mapProvider.maxZoom,
                          ),
                          children: [
                            TileLayer(
                              urlTemplate: tileUrl,
                              userAgentPackageName: 'com.geovision.geovision',
                              maxZoom: mapProvider.maxZoom,
                            ),
                            MarkerLayer(
                              markers: [
                                Marker(
                                  point: position,
                                  width: 56,
                                  height: 56,
                                  child: const Icon(
                                    Icons.location_on,
                                    size: 52,
                                    color: GvColors.critical,
                                  ),
                                ),
                              ],
                            ),
                            RichAttributionWidget(
                              attributions: [
                                TextSourceAttribution(mapProvider.attribution),
                              ],
                            ),
                          ],
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
                    const SizedBox(height: GvSpacing.xs),
                    Text(
                      mapProvider.displayName,
                      style: const TextStyle(
                        color: GvColors.textMuted,
                        fontSize: 12,
                      ),
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

class _DemoMapSurface extends StatelessWidget {
  const _DemoMapSurface();

  @override
  Widget build(BuildContext context) => Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
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
      );
}
