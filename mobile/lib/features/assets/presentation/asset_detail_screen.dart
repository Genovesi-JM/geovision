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

enum _AssetSection {
  overview,
  map,
  actions,
  monitoring,
  reports,
  history,
  services,
}

extension on _AssetSection {
  String get label => switch (this) {
        _AssetSection.overview => 'Overview',
        _AssetSection.map => 'Map',
        _AssetSection.actions => 'Actions',
        _AssetSection.monitoring => 'Monitoring',
        _AssetSection.reports => 'Reports',
        _AssetSection.history => 'History',
        _AssetSection.services => 'Services',
      };
}

class AssetDetailScreen extends ConsumerStatefulWidget {
  const AssetDetailScreen({super.key, required this.assetId});

  final String assetId;

  @override
  ConsumerState<AssetDetailScreen> createState() => _AssetDetailScreenState();
}

class _AssetDetailScreenState extends ConsumerState<AssetDetailScreen> {
  _AssetSection _selected = _AssetSection.overview;

  @override
  Widget build(BuildContext context) {
    final asset = ref.watch(customerAssetDetailProvider(widget.assetId));
    return Scaffold(
      appBar: AppBar(title: const Text('Asset detail')),
      body: asset.when(
        loading: () => const GvLoading(label: 'Loading asset…'),
        error: (_, __) => GvErrorState(
          message: 'This asset could not be loaded.',
          onRetry: () =>
              ref.invalidate(customerAssetDetailProvider(widget.assetId)),
        ),
        data: (item) {
          if (item == null) {
            return const GvEmpty(
              message: 'Asset not found in this workspace.',
              icon: Icons.terrain_outlined,
            );
          }
          final capabilities =
              ref.watch(customerExperienceProvider).valueOrNull;
          final sections = <_AssetSection>[
            _AssetSection.overview,
            if (item.hasLocation) _AssetSection.map,
            if (capabilities?.hasCapability('actions') == true)
              _AssetSection.actions,
            if (capabilities?.hasCapability('devices') == true)
              _AssetSection.monitoring,
            if (capabilities?.hasCapability('reports') == true)
              _AssetSection.reports,
            _AssetSection.history,
            if (capabilities?.hasCapability('services') == true)
              _AssetSection.services,
          ];
          final selected =
              sections.contains(_selected) ? _selected : _AssetSection.overview;
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              _AssetHeader(asset: item),
              const SizedBox(height: GvSpacing.md),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Wrap(
                  spacing: GvSpacing.sm,
                  children: [
                    for (final section in sections)
                      ChoiceChip(
                        label: Text(section.label),
                        selected: selected == section,
                        onSelected: (_) => setState(() => _selected = section),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: GvSpacing.md),
              _SectionContent(asset: item, section: selected),
            ],
          );
        },
      ),
    );
  }
}

class _AssetHeader extends StatelessWidget {
  const _AssetHeader({required this.asset});

  final CustomerAsset asset;

  @override
  Widget build(BuildContext context) => GvCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              asset.name,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: GvSpacing.xs),
            Text(
              '${_friendly(asset.assetType)} · ${_friendly(asset.sector)}',
              style: const TextStyle(color: GvColors.accentCyan),
            ),
            if (asset.locationLabel.isNotEmpty)
              Text(
                asset.locationLabel,
                style: const TextStyle(color: GvColors.textSecondary),
              ),
            const SizedBox(height: GvSpacing.sm),
            Chip(label: Text(_friendly(asset.status))),
          ],
        ),
      );
}

class _SectionContent extends StatelessWidget {
  const _SectionContent({required this.asset, required this.section});

  final CustomerAsset asset;
  final _AssetSection section;

  @override
  Widget build(BuildContext context) => switch (section) {
        _AssetSection.overview => _Overview(asset: asset),
        _AssetSection.map => _DestinationCard(
            icon: Icons.map_outlined,
            title: 'Asset map',
            body: 'Open the recorded location and spatial context.',
            button: 'Open map',
            onPressed: () => context.push('/assets/${asset.id}/map'),
          ),
        _AssetSection.actions => _DestinationCard(
            icon: Icons.task_alt_outlined,
            title: 'Asset actions',
            body: 'Review critical, attention, scheduled, and completed work.',
            button: 'Open actions',
            onPressed: () => context.push('/actions?asset_id=${asset.id}'),
          ),
        _AssetSection.monitoring => _DestinationCard(
            icon: Icons.sensors_outlined,
            title: 'Monitoring',
            body: 'Review connected GeoVision devices and current readings.',
            button: 'Open monitoring',
            onPressed: () => context.push('/devices'),
          ),
        _AssetSection.reports => _DestinationCard(
            icon: Icons.description_outlined,
            title: 'Reports',
            body: 'Open published reports available to this workspace.',
            button: 'Open reports',
            onPressed: () => context.push('/reports?asset_id=${asset.id}'),
          ),
        _AssetSection.history => _History(asset: asset),
        _AssetSection.services => _DestinationCard(
            icon: Icons.design_services_outlined,
            title: 'GeoVision services',
            body: 'Choose a service or request work for this existing asset.',
            button: 'Explore services',
            onPressed: () => context.push('/services'),
            secondaryButton: 'Request work',
            onSecondaryPressed: () => context.push('/work/new'),
          ),
      };
}

class _Overview extends StatelessWidget {
  const _Overview({required this.asset});

  final CustomerAsset asset;

  @override
  Widget build(BuildContext context) => GvCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              asset.description.isEmpty
                  ? 'No description has been added.'
                  : asset.description,
              style: const TextStyle(
                color: GvColors.textSecondary,
                height: 1.4,
              ),
            ),
            const SizedBox(height: GvSpacing.md),
            Text('${asset.childrenCount} linked sub-assets'),
            if (asset.parentAssetId case final parentId?)
              Text(
                'Part of $parentId',
                style: const TextStyle(color: GvColors.textMuted),
              ),
          ],
        ),
      );
}

class _History extends StatelessWidget {
  const _History({required this.asset});

  final CustomerAsset asset;

  @override
  Widget build(BuildContext context) => GvCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Asset record',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: GvSpacing.sm),
            if (asset.updatedAt case final updated?)
              Text('Last updated ${updated.toLocal()}'),
            if (asset.metadata.isEmpty)
              const Text(
                'No additional history is available yet.',
                style: TextStyle(color: GvColors.textSecondary),
              )
            else
              for (final entry in asset.metadata.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: GvSpacing.xs),
                  child: Text('${_friendly(entry.key)}: ${entry.value}'),
                ),
          ],
        ),
      );
}

class _DestinationCard extends StatelessWidget {
  const _DestinationCard({
    required this.icon,
    required this.title,
    required this.body,
    required this.button,
    required this.onPressed,
    this.secondaryButton,
    this.onSecondaryPressed,
  });

  final IconData icon;
  final String title;
  final String body;
  final String button;
  final VoidCallback onPressed;
  final String? secondaryButton;
  final VoidCallback? onSecondaryPressed;

  @override
  Widget build(BuildContext context) => GvCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Icon(icon, color: GvColors.accentCyan, size: 34),
            const SizedBox(height: GvSpacing.sm),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            Text(
              body,
              textAlign: TextAlign.center,
              style: const TextStyle(color: GvColors.textSecondary),
            ),
            const SizedBox(height: GvSpacing.md),
            FilledButton(onPressed: onPressed, child: Text(button)),
            if (secondaryButton != null) ...[
              const SizedBox(height: GvSpacing.sm),
              OutlinedButton(
                onPressed: onSecondaryPressed,
                child: Text(secondaryButton!),
              ),
            ],
          ],
        ),
      );
}

String _friendly(String value) => value
    .toLowerCase()
    .split('_')
    .map((word) =>
        word.isEmpty ? word : '${word[0].toUpperCase()}${word.substring(1)}')
    .join(' ');
