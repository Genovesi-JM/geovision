import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../app/providers.dart';
import '../../../core/localization/journey_copy.dart';
import '../../reports/data/report_files.dart';
import '../data/evidence_repository.dart';

class EvidenceTile extends ConsumerStatefulWidget {
  const EvidenceTile(
      {super.key,
      required this.requestId,
      required this.file,
      this.pending = false});
  final String requestId;
  final UploadedEvidence file;
  final bool pending;
  @override
  ConsumerState<EvidenceTile> createState() => _EvidenceTileState();
}

class _EvidenceTileState extends ConsumerState<EvidenceTile> {
  bool _busy = false;
  String? _error;
  Future<void> _open(bool save) async {
    final box = context.findRenderObject() as RenderBox;
    final origin = box.localToGlobal(Offset.zero) & box.size;
    final api = ref.read(apiClientProvider);
    final workspace = api.workspaceId;
    final tokens = ref.read(secureTokenStoreProvider);
    final token = await tokens.readAccess();
    if (!mounted || token == null) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final bytes = await ref
          .read(evidenceRepositoryProvider)
          .download(widget.requestId, widget.file);
      if (!mounted ||
          api.workspaceId != workspace ||
          await tokens.readAccess() != token) {
        return;
      }
      await ref.read(reportFilesProvider).presentFile(bytes,
          filename: widget.file.filename,
          mime: widget.file.mime,
          save: save,
          origin: origin);
    } catch (_) {
      if (mounted) {
        setState(() => _error = journeyText(
            context,
            'No se pudo abrir el archivo. Comprueba la conexión y tus permisos e inténtalo de nuevo.',
            'Could not open the file. Check your connection and permissions, then retry.',
            pt: 'Não foi possível abrir o ficheiro. Verifique a ligação e as suas permissões e tente novamente.'));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.attach_file),
            title: Text(widget.file.filename),
            subtitle:
                Text('${(widget.file.size / 1024).toStringAsFixed(0)} KB'),
            onTap: _busy || widget.pending ? null : () => _open(false),
            trailing: IconButton(
                tooltip: journeyText(
                    context, 'Guardar o compartir', 'Save or share',
                    pt: 'Guardar ou partilhar'),
                onPressed: _busy || widget.pending ? null : () => _open(true),
                icon: const Icon(Icons.download_outlined))),
        if (widget.pending)
          Text(journeyText(
              context,
              'El archivo se podrá abrir cuando se confirme la solicitud.',
              'The file can be opened once the request is confirmed.',
              pt: 'O ficheiro poderá ser aberto quando o pedido for confirmado.')),
        if (_busy) const LinearProgressIndicator(),
        if (_error != null) Text(_error!),
      ]);
}
