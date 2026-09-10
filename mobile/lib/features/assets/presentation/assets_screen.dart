import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../../account/data/customer_experience_repository.dart';
import '../data/assets_repository.dart';
import '../domain/customer_asset.dart';

enum _AssetsView { list, map }

class AssetsScreen extends ConsumerStatefulWidget {
  const AssetsScreen({super.key});

  @override
  ConsumerState<AssetsScreen> createState() => _AssetsScreenState();
}

class _AssetsScreenState extends ConsumerState<AssetsScreen> {
  String _query = '';
  _AssetsView _view = _AssetsView.list;

  Future<void> _refresh() async {
    ref.invalidate(customerAssetsProvider);
    await ref.read(customerAssetsProvider.future);
  }

  @override
  Widget build(BuildContext context) {
    final assets = ref.watch(customerAssetsProvider);
    final experience = ref.watch(customerExperienceProvider).valueOrNull;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Assets'),
        actions: [
          if (experience?.hasPermission('asset:create') == true)
            IconButton(
              tooltip: 'Add asset',
              onPressed: () => context.push('/assets/new'),
              icon: const Icon(Icons.add_location_alt_outlined),
            ),
        ],
      ),
      body: assets.when(
        loading: () => const GvLoading(label: 'Loading assets…'),
        error: (_, __) => GvErrorState(
          message: 'Assets could not be loaded.',
          onRetry: () => ref.invalidate(customerAssetsProvider),
        ),
        data: (envelope) {
          final query = _query.trim().toLowerCase();
          final filtered = envelope.value.where((asset) {
            return query.isEmpty ||
                asset.name.toLowerCase().contains(query) ||
                asset.locationLabel.toLowerCase().contains(query) ||
                asset.assetType.toLowerCase().contains(query) ||
                asset.sector.toLowerCase().contains(query);
          }).toList();
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(
                  GvSpacing.lg,
                  GvSpacing.md,
                  GvSpacing.lg,
                  GvSpacing.sm,
                ),
                child: TextField(
                  onChanged: (value) => setState(() => _query = value),
                  decoration: const InputDecoration(
                    hintText: 'Search every asset',
                    prefixIcon: Icon(Icons.search),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: GvSpacing.lg),
                child: Row(
                  children: [
                    SegmentedButton<_AssetsView>(
                      showSelectedIcon: false,
                      segments: const [
                        ButtonSegment(
                          value: _AssetsView.list,
                          icon: Icon(Icons.view_list_outlined),
                          label: Text('List'),
                        ),
                        ButtonSegment(
                          value: _AssetsView.map,
                          icon: Icon(Icons.map_outlined),
                          label: Text('Map'),
                        ),
                      ],
                      selected: {_view},
                      onSelectionChanged: (selection) =>
                          setState(() => _view = selection.first),
                    ),
                    const Spacer(),
                    Text(
                      '${filtered.length}',
                      semanticsLabel: '${filtered.length} assets',
                      style: const TextStyle(color: GvColors.textMuted),
                    ),
                  ],
                ),
              ),
              if (envelope.fromCache)
                const Padding(
                  padding: EdgeInsets.only(top: GvSpacing.sm),
                  child: Text(
                    'Offline copy',
                    style: TextStyle(color: GvColors.medium, fontSize: 11),
                  ),
                ),
              const SizedBox(height: GvSpacing.sm),
              Expanded(
                child: filtered.isEmpty
                    ? RefreshIndicator(
                        onRefresh: _refresh,
                        child: ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: const [
                            SizedBox(
                              height: 360,
                              child: GvEmpty(
                                message: 'No assets match this view.',
                                icon: Icons.terrain_outlined,
                              ),
                            ),
                          ],
                        ),
                      )
                    : _view == _AssetsView.list
                        ? _AssetList(assets: filtered, onRefresh: _refresh)
                        : _AssetMapOverview(
                            assets: filtered,
                            onRefresh: _refresh,
                          ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _AssetList extends StatelessWidget {
  const _AssetList({required this.assets, required this.onRefresh});

  final List<CustomerAsset> assets;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView.separated(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(GvSpacing.lg),
          itemCount: assets.length,
          separatorBuilder: (_, __) => const SizedBox(height: GvSpacing.sm),
          itemBuilder: (context, index) {
            final asset = assets[index];
            return GvCard(
              onTap: () => context.push('/assets/${asset.id}'),
              child: Row(
                children: [
                  CircleAvatar(
                    backgroundColor: _assetColor(asset).withValues(alpha: 0.16),
                    child: Icon(_assetIcon(asset), color: _assetColor(asset)),
                  ),
                  const SizedBox(width: GvSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          asset.name,
                          style: const TextStyle(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          '${_friendly(asset.assetType)} · ${_friendly(asset.sector)}',
                          style: const TextStyle(
                            color: GvColors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                        if (asset.locationLabel.isNotEmpty)
                          Text(
                            asset.locationLabel,
                            style: const TextStyle(
                              color: GvColors.textMuted,
                              fontSize: 11,
                            ),
                          ),
                      ],
                    ),
                  ),
                  _StatusDot(status: asset.status),
                  const SizedBox(width: GvSpacing.xs),
                  const Icon(Icons.chevron_right, color: GvColors.textMuted),
                ],
              ),
            );
          },
        ),
      );
}

class _AssetMapOverview extends StatelessWidget {
  const _AssetMapOverview({required this.assets, required this.onRefresh});

  final List<CustomerAsset> assets;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    final located = assets.where((asset) => asset.hasLocation).toList();
    if (located.isEmpty) {
      return RefreshIndicator(
        onRefresh: onRefresh,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: const [
            SizedBox(
              height: 360,
              child: GvEmpty(
                message: 'These assets do not have map locations yet.',
                icon: Icons.location_off_outlined,
              ),
            ),
          ],
        ),
      );
    }
    final minLat =
        located.map((asset) => asset.latitude!).reduce((a, b) => a < b ? a : b);
    final maxLat =
        located.map((asset) => asset.latitude!).reduce((a, b) => a > b ? a : b);
    final minLng = located
        .map((asset) => asset.longitude!)
        .reduce((a, b) => a < b ? a : b);
    final maxLng = located
        .map((asset) => asset.longitude!)
        .reduce((a, b) => a > b ? a : b);

    return Padding(
      padding: const EdgeInsets.all(GvSpacing.lg),
      child: Semantics(
        container: true,
        label: 'Asset map with ${located.length} located assets',
        child: LayoutBuilder(
          builder: (context, constraints) {
            const markerSize = 48.0;
            final width = constraints.maxWidth - markerSize;
            final height = constraints.maxHeight - markerSize;
            return Container(
              decoration: BoxDecoration(
                color: GvColors.surfaceDeep,
                borderRadius: BorderRadius.circular(GvSpacing.radiusLg),
                border: Border.all(color: GvColors.border),
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFF092337), Color(0xFF071A20)],
                ),
              ),
              child: Stack(
                children: [
                  const Positioned(
                    left: 16,
                    top: 16,
                    child: Text(
                      'Workspace asset map',
                      style: TextStyle(
                        color: GvColors.textSecondary,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  for (final asset in located)
                    Positioned(
                      left: _fraction(asset.longitude!, minLng, maxLng) * width,
                      top: (1 - _fraction(asset.latitude!, minLat, maxLat)) *
                          height,
                      child: Semantics(
                        button: true,
                        label: '${asset.name}, open asset',
                        child: IconButton.filled(
                          tooltip: asset.name,
                          onPressed: () => context.push('/assets/${asset.id}'),
                          icon: Icon(_assetIcon(asset)),
                        ),
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }
}

class _StatusDot extends StatelessWidget {
  const _StatusDot({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) => Semantics(
        label: 'Status ${_friendly(status)}',
        child: Container(
          width: 9,
          height: 9,
          decoration: BoxDecoration(
            color: status == 'active'
                ? GvColors.accentGreen
                : status == 'draft'
                    ? GvColors.medium
                    : GvColors.textMuted,
            shape: BoxShape.circle,
          ),
        ),
      );
}

double _fraction(double value, double min, double max) =>
    max == min ? 0.5 : ((value - min) / (max - min)).clamp(0, 1);

String _friendly(String value) => value
    .toLowerCase()
    .split('_')
    .map((word) =>
        word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}')
    .join(' ');

IconData _assetIcon(CustomerAsset asset) => switch (asset.assetType) {
      'FARM' || 'FIELD' => Icons.agriculture_outlined,
      'ROAD' || 'BRIDGE' || 'RAILWAY' => Icons.route_outlined,
      'MINE' || 'QUARRY' || 'STOCKPILE' => Icons.landscape_outlined,
      'PORT' || 'TERMINAL' || 'QUAY' => Icons.directions_boat_outlined,
      'BUILDING' || 'FACILITY' || 'WAREHOUSE' => Icons.domain_outlined,
      'IOT_DEVICE' => Icons.sensors_outlined,
      _ => Icons.terrain_outlined,
    };

Color _assetColor(CustomerAsset asset) => switch (asset.sector) {
      'AGRICULTURE' => GvColors.accentGreen,
      'ENVIRONMENTAL' => GvColors.accentCyan,
      'MINING' => GvColors.medium,
      'INFRASTRUCTURE' => GvColors.accentSky,
      _ => GvColors.textSecondary,
    };
