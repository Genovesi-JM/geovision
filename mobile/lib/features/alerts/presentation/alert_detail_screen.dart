import '../../account/data/customer_experience_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../app/providers.dart';
import '../../../core/localization/journey_copy.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_section_header.dart';
import '../../../core/widgets/gv_states.dart';
import '../../../core/widgets/severity_chip.dart';
import '../../../l10n/app_localizations.dart';
import '../data/alerts_repository.dart';
import 'alert_copy.dart';

class AlertDetailScreen extends ConsumerWidget {
  const AlertDetailScreen({super.key, required this.alertId});
  final String alertId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alertsAsync = ref.watch(alertsProvider);
    final text = AppLocalizations.of(context);
    final copy = AlertCopy.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(text.navAlerts)),
      body: alertsAsync.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(message: '$e'),
        data: (env) {
          final matches = env.value.where((a) => a.id == alertId);
          if (matches.isEmpty) {
            return GvEmpty(message: copy.alertNotFound);
          }
          final a = matches.first;
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              Row(
                children: [
                  SeverityChip(severityFromString(a.severity)),
                  const SizedBox(width: GvSpacing.sm),
                  Text(
                      DateFormat.yMMMd().add_Hm().format(a.createdAt.toLocal()),
                      style: const TextStyle(
                          color: GvColors.textMuted, fontSize: 12)),
                ],
              ),
              const SizedBox(height: GvSpacing.md),
              Text(copy.title(a),
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.w800)),
              const SizedBox(height: GvSpacing.sm),
              Text(copy.description(a),
                  style: const TextStyle(
                      color: GvColors.textSecondary, height: 1.4)),
              const SizedBox(height: GvSpacing.md),
              if (a.location != null)
                GvCard(
                  child: Row(children: [
                    const Icon(Icons.place_outlined,
                        color: GvColors.accentCyan),
                    const SizedBox(width: GvSpacing.md),
                    Expanded(child: Text(a.location!)),
                    if (a.siteId != null)
                      TextButton(
                        onPressed: () =>
                            context.push('/assets/${a.siteId}/map'),
                        child: Text(copy.viewOnMap),
                      ),
                  ]),
                ),
              if (a.recommendation != null) ...[
                const SizedBox(height: GvSpacing.md),
                GvSectionHeader(title: text.recommendedAction),
                GvCard(
                  child: Row(children: [
                    const Icon(Icons.lightbulb_outline, color: GvColors.medium),
                    const SizedBox(width: GvSpacing.md),
                    Expanded(
                        child: Text(copy.recommendation(a)!,
                            style: const TextStyle(height: 1.4))),
                  ]),
                ),
              ],
              if (a.evidence.isNotEmpty) ...[
                const SizedBox(height: GvSpacing.md),
                GvSectionHeader(title: copy.evidence),
                GvCard(
                    child: Text(a.evidence.join(', '),
                        style: const TextStyle(color: GvColors.textSecondary))),
              ],
              Text(journeyText(context,
                'Confirmar lectura registra la recepción. No resuelve el problema ni envía comandos.',
                'Acknowledgement records receipt. It does not resolve the issue or send device commands.',
                pt: 'Confirmar leitura regista a receção. Não resolve o problema nem envia comandos.')),
              const SizedBox(height: GvSpacing.xl),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: a.resolved || a.acknowledged || (!ref.watch(appConfigProvider).demoMode &&
                              (a.source != 'iot' || ref.watch(customerExperienceProvider).valueOrNull?.hasPermission('workspace:contribute') != true))
                          ? null
                          : () async {
                              try {
                                await ref.read(alertsRepositoryProvider).acknowledge(a.id);
                                ref.invalidate(alertsProvider);
                              } catch (_) {
                                if (context.mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(journeyText(context,
                                  'No se confirmó la lectura. Comprueba conexión y permisos y actualiza el estado.',
                                  'Acknowledgement was not confirmed. Check connection and access, then refresh the status.',
                                  pt: 'A leitura não foi confirmada. Verifique a ligação e as permissões e atualize o estado.'))));
                                }
                              }
                            },
                      icon: const Icon(Icons.check),
                      label: Text(a.acknowledged
                          ? copy.acknowledged
                          : text.acknowledge),
                    ),
                  ),
                  const SizedBox(width: GvSpacing.md),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: () => context.go(Uri(
                          path: '/work/new',
                          queryParameters: {
                            if (a.siteId != null) 'asset_id': a.siteId!,
                            'description': copy.title(a)
                          }).toString()),
                      icon: const Icon(Icons.build_outlined),
                      label: Text(text.requestIntervention),
                    ),
                  ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}
