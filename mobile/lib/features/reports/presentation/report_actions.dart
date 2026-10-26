import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/localization/journey_copy.dart';
import '../data/report_files.dart';
import '../data/reports_repository.dart';

class ReportActions extends ConsumerStatefulWidget {
  const ReportActions({super.key, required this.reportId});
  final String reportId;
  @override
  ConsumerState<ReportActions> createState() => _ReportActionsState();
}

class _ReportActionsState extends ConsumerState<ReportActions> {
  bool _busy = false;
  String? _error;

  Future<void> _open(bool save) async {
    final box = context.findRenderObject() as RenderBox;
    final origin = box.localToGlobal(Offset.zero) & box.size;
    final files = ref.read(reportFilesProvider);
    final api = ref.read(apiClientProvider);
    final workspace = api.workspaceId;
    final tokens = ref.read(secureTokenStoreProvider);
    final token = await tokens.readAccess();
    if (!mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final bytes =
          await ref.read(reportsRepositoryProvider).download(widget.reportId);
      // A workspace switch or logout during download must not open old content.
      if (!mounted ||
          api.workspaceId != workspace ||
          await tokens.readAccess() != token) {
        return;
      }
      if (token == null) return;
      await files.present(bytes, save: save, origin: origin);
    } catch (_) {
      if (mounted) {
        setState(() => _error = journeyText(
            context,
            'No se pudo abrir el PDF. Comprueba tu conexión y tus permisos e inténtalo de nuevo.',
            'Could not open the PDF. Check your connection and permissions, then try again.',
            pt: 'Não foi possível abrir o PDF. Verifique a ligação e as suas permissões e tente novamente.'));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final demo = ref.watch(appConfigProvider).demoMode;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      if (demo)
        Text(journeyText(
            context,
            'Informe de demostración: no hay un PDF real.',
            'Demo report: no real PDF is attached.',
            pt: 'Relatório de demonstração: não existe um PDF real associado.')),
      if (_error != null) Text(_error!),
      if (_busy) const LinearProgressIndicator(),
      FilledButton.icon(
        onPressed: demo || _busy ? null : () => _open(false),
        icon: const Icon(Icons.open_in_new),
        label: Text(
            journeyText(context, 'Abrir PDF', 'Open PDF', pt: 'Abrir PDF')),
      ),
      OutlinedButton.icon(
        onPressed: demo || _busy ? null : () => _open(true),
        icon: const Icon(Icons.download_outlined),
        label: Text(journeyText(
            context, 'Guardar o compartir PDF', 'Save or share PDF',
            pt: 'Guardar ou partilhar PDF')),
      ),
    ]);
  }
}
