import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/drones_repository.dart';
import '../domain/drone.dart';

class DronesScreen extends ConsumerWidget {
  const DronesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final aircraft = ref.watch(aircraftProvider);
    final missions = ref.watch(droneMissionsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Drones e missões')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(aircraftProvider);
          ref.invalidate(droneMissionsProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(GvSpacing.lg),
          children: [
            const _SafetyNotice(),
            const SizedBox(height: GvSpacing.lg),
            const Text('Aeronaves',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: GvSpacing.sm),
            aircraft.when(
              loading: () => const GvLoading(),
              error: (error, _) => GvErrorState(message: '$error'),
              data: (items) => Column(
                children: items
                    .map((item) => Padding(
                          padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                          child: _AircraftCard(aircraft: item),
                        ))
                    .toList(),
              ),
            ),
            const SizedBox(height: GvSpacing.lg),
            const Text('Missões planeadas',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: GvSpacing.sm),
            missions.when(
              loading: () => const GvLoading(),
              error: (error, _) => GvErrorState(message: '$error'),
              data: (items) => items.isEmpty
                  ? const GvEmpty(
                      message: 'Ainda não existem missões.',
                      icon: Icons.route_outlined)
                  : Column(
                      children: items
                          .map((mission) => GvCard(
                                child: ListTile(
                                  contentPadding: EdgeInsets.zero,
                                  leading: const Icon(Icons.grid_4x4,
                                      color: GvColors.accentCyan),
                                  title: Text(mission.name),
                                  subtitle: Text(
                                      '${mission.altitudeM} m · ${mission.frontOverlap}/${mission.sideOverlap}% overlap'),
                                  trailing: Chip(label: Text(mission.status)),
                                ),
                              ))
                          .toList(),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SafetyNotice extends StatelessWidget {
  const _SafetyNotice();
  @override
  Widget build(BuildContext context) => GvCard(
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.health_and_safety_outlined, color: GvColors.medium),
          const SizedBox(width: GvSpacing.sm),
          Expanded(
            child: Text(
              'A GeoVision planeia e acompanha a missão. A descolagem exige piloto, verificação do espaço aéreo, meteorologia, pessoas e aeronave.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ]),
      );
}

class _AircraftCard extends ConsumerWidget {
  const _AircraftCard({required this.aircraft});
  final GvDrone aircraft;

  @override
  Widget build(BuildContext context, WidgetRef ref) => GvCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(Icons.flight,
                color: aircraft.sdkSupported
                    ? GvColors.accentGreen
                    : GvColors.accentSky),
            const SizedBox(width: GvSpacing.sm),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(aircraft.name,
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                    Text(aircraft.model,
                        style: const TextStyle(
                            color: GvColors.textMuted, fontSize: 12)),
                  ]),
            ),
            Chip(
              label: Text(aircraft.sdkSupported ? 'Automação' : 'Importação'),
              avatar: Icon(
                  aircraft.sdkSupported ? Icons.route : Icons.photo_library,
                  size: 16),
            ),
          ]),
          const SizedBox(height: GvSpacing.sm),
          Wrap(
            spacing: 6,
            children: aircraft.capabilities
                .map((capability) => Chip(
                    visualDensity: VisualDensity.compact,
                    label: Text(capability.replaceAll('_', ' '))))
                .toList(),
          ),
          const SizedBox(height: GvSpacing.sm),
          Row(children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: () => _readiness(context, ref),
                icon: const Icon(Icons.fact_check_outlined),
                label: const Text('Verificar'),
              ),
            ),
            if (!aircraft.sdkSupported) ...[
              const SizedBox(width: GvSpacing.sm),
              Expanded(
                child: FilledButton.icon(
                  onPressed: () => _importMedia(context, ref),
                  icon: const Icon(Icons.add_photo_alternate_outlined),
                  label: const Text('Importar voo'),
                ),
              ),
            ],
          ]),
        ]),
      );

  Future<void> _readiness(BuildContext context, WidgetRef ref) async {
    final result = await ref.read(dronesRepositoryProvider).readiness(aircraft);
    if (!context.mounted) return;
    await _show(context, result.message);
  }

  Future<void> _importMedia(BuildContext context, WidgetRef ref) async {
    final files = await ImagePicker().pickMultiImage(imageQuality: 92);
    if (!context.mounted) return;
    final result = await ref
        .read(dronesRepositoryProvider)
        .stageMedia(aircraft, files.map((file) => file.path).toList());
    if (!context.mounted) return;
    await _show(context, result.message);
  }

  Future<void> _show(BuildContext context, String message) => showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(aircraft.model),
          content: Text(message),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('OK')),
          ],
        ),
      );
}
