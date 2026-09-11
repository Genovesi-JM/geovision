import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../../../app/providers.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../../../integrations/maps/external_map_navigation.dart';
import '../../sites/data/location_repository.dart';
import '../../sites/domain/location_search.dart';
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
              _RoutePlanner(
                destinationLatitude: item.latitude!,
                destinationLongitude: item.longitude!,
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
                    const SizedBox(height: GvSpacing.md),
                    Wrap(
                      spacing: GvSpacing.sm,
                      runSpacing: GvSpacing.sm,
                      children: [
                        OutlinedButton.icon(
                          onPressed: () => _openDirections(
                            context,
                            const ExternalMapNavigation().googleDirections(
                              latitude: item.latitude!,
                              longitude: item.longitude!,
                            ),
                          ),
                          icon: const Icon(Icons.directions_outlined),
                          label: const Text('Google Maps'),
                        ),
                        OutlinedButton.icon(
                          onPressed: () => _openDirections(
                            context,
                            const ExternalMapNavigation().appleDirections(
                              latitude: item.latitude!,
                              longitude: item.longitude!,
                              label: item.name,
                            ),
                          ),
                          icon: const Icon(Icons.map_outlined),
                          label: const Text('Apple Maps'),
                        ),
                      ],
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

  Future<void> _openDirections(BuildContext context, Uri uri) async {
    final opened = await const ExternalMapNavigation().open(uri);
    if (!opened && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('The map application could not be opened.')),
      );
    }
  }
}

class _RoutePlanner extends ConsumerStatefulWidget {
  const _RoutePlanner({
    required this.destinationLatitude,
    required this.destinationLongitude,
  });

  final double destinationLatitude;
  final double destinationLongitude;

  @override
  ConsumerState<_RoutePlanner> createState() => _RoutePlannerState();
}

class _RoutePlannerState extends ConsumerState<_RoutePlanner> {
  bool loading = false;
  RouteEstimate? estimate;
  String? error;

  @override
  Widget build(BuildContext context) => GvCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Row(children: [
              Icon(Icons.route_outlined, color: GvColors.accentCyan),
              SizedBox(width: GvSpacing.sm),
              Expanded(
                child: Text('Driving route estimate',
                    style: TextStyle(fontWeight: FontWeight.w800)),
              ),
            ]),
            const SizedBox(height: GvSpacing.xs),
            if (estimate == null)
              const Text(
                'Use your current position to estimate distance and travel time.',
                style: TextStyle(color: GvColors.textSecondary),
              )
            else ...[
              Text(
                '${_distance(estimate!.distanceMeters)} • '
                '${_duration(estimate!.durationSeconds)}',
                style:
                    const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
              ),
              Text(
                estimate!.simulated
                    ? 'Demonstration estimate — not live navigation'
                    : estimate!.trafficAware
                        ? 'Live provider estimate with traffic'
                        : 'Provider estimate without live traffic',
                style: const TextStyle(
                    color: GvColors.textSecondary, fontSize: 12),
              ),
            ],
            if (error != null) ...[
              const SizedBox(height: GvSpacing.xs),
              Text(error!, style: const TextStyle(color: GvColors.critical)),
            ],
            const SizedBox(height: GvSpacing.sm),
            OutlinedButton.icon(
              onPressed: loading ? null : _estimate,
              icon: loading
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.my_location),
              label: Text(estimate == null ? 'Estimate route' : 'Refresh'),
            ),
          ],
        ),
      );

  Future<void> _estimate() async {
    final languageCode = Localizations.localeOf(context).languageCode;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw StateError('Enable location services on the device.');
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        throw StateError(
            'Location permission is required to estimate a route.');
      }
      final origin = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 20),
        ),
      );
      final result =
          await ref.read(locationRepositoryProvider).computeDrivingRoute(
                originLatitude: origin.latitude,
                originLongitude: origin.longitude,
                destinationLatitude: widget.destinationLatitude,
                destinationLongitude: widget.destinationLongitude,
                languageCode: languageCode,
              );
      if (mounted) setState(() => estimate = result);
    } catch (failure) {
      if (mounted) setState(() => error = '$failure');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  static String _distance(int meters) =>
      meters < 1000 ? '$meters m' : '${(meters / 1000).toStringAsFixed(1)} km';

  static String _duration(int seconds) {
    final minutes = (seconds / 60).ceil();
    if (minutes < 60) return '$minutes min';
    final hours = minutes ~/ 60;
    final remainder = minutes % 60;
    return remainder == 0 ? '$hours h' : '$hours h $remainder min';
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
