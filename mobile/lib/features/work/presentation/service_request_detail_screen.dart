import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/localization/journey_copy.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/work_repository.dart';
import 'evidence_tile.dart';

class ServiceRequestDetailScreen extends ConsumerWidget {
  const ServiceRequestDetailScreen({super.key, required this.requestId});
  final String requestId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final request = ref.watch(serviceRequestDetailProvider(requestId));
    return Scaffold(
      appBar: AppBar(
          title: Text(journeyText(
              context, 'Solicitud de servicio', 'Service request',
              pt: 'Pedido de serviço'))),
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
              if (item.pendingSync)
                Text(journeyText(
                    context,
                    'Guardada en este dispositivo. GeoVision todavía no ha recibido esta solicitud.',
                    'Saved on this device. GeoVision has not received this request yet.',
                    pt: 'Guardado neste dispositivo. A GeoVision ainda não recebeu este pedido.')),
              if (!item.pendingSync && item.status == 'submitted')
                Text(journeyText(
                    context,
                    'Solicitud recibida. Confirmaremos el alcance, el presupuesto y la fecha antes de iniciar el trabajo.',
                    'Request received. Scope, quote and scheduling will be confirmed before work starts.',
                    pt: 'Pedido recebido. O âmbito, o orçamento e o agendamento serão confirmados antes do início do trabalho.')),
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
                Text(
                    journeyText(context, 'Archivos adjuntos', 'Attachments',
                        pt: 'Anexos'),
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w800)),
                for (final file in item.attachmentFiles)
                  EvidenceTile(
                      requestId: item.id,
                      file: file,
                      pending: item.pendingSync),
                if (item.attachmentFiles.length < item.attachments.length)
                  Text(journeyText(
                      context,
                      'Algunos adjuntos antiguos o eliminados ya no están disponibles.',
                      'Some older or removed attachments are no longer available.',
                      pt: 'Alguns anexos antigos ou removidos já não estão disponíveis.')),
              ],
              if (item.resultReportId case final reportId?) ...[
                const SizedBox(height: GvSpacing.md),
                FilledButton.icon(
                  onPressed: () => context.push('/reports/$reportId'),
                  icon: const Icon(Icons.description_outlined),
                  label: Text(journeyText(context, 'Abrir informe publicado',
                      'Open published report',
                      pt: 'Abrir relatório publicado')),
                ),
              ],
              if (item.siteId.isNotEmpty || item.resultAssetId != null) ...[
                const SizedBox(height: GvSpacing.sm),
                OutlinedButton.icon(
                  onPressed: () => context
                      .push('/assets/${item.resultAssetId ?? item.siteId}'),
                  icon: const Icon(Icons.landscape_outlined),
                  label: Text(journeyText(
                      context, 'Abrir activo', 'Open existing asset',
                      pt: 'Abrir ativo existente')),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}
