import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import '../../../l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../app/providers.dart';
import '../../account/data/customer_experience_repository.dart';
import '../data/evidence_repository.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../assets/data/assets_repository.dart';
import '../../assets/domain/customer_asset.dart';
import '../../../core/localization/journey_copy.dart';
import '../data/work_repository.dart';
import '../domain/service_request.dart';

class NewRequestScreen extends ConsumerStatefulWidget {
  const NewRequestScreen(
      {super.key, this.assetId, this.initialDescription, this.initialType});
  final String? assetId;
  final String? initialDescription;
  final String? initialType;
  @override
  ConsumerState<NewRequestScreen> createState() => _NewRequestScreenState();
}

class _NewRequestScreenState extends ConsumerState<NewRequestScreen> {
  ServiceType _type = ServiceType.inspection;
  String _urgency = 'normal';
  String? _siteId;
  final _desc = TextEditingController();
  @override
  void initState() {
    super.initState();
    _siteId = widget.assetId;
    _desc.text = widget.initialDescription ?? '';
    _type = ServiceType.values
            .where((t) => t.name == widget.initialType)
            .firstOrNull ??
        ServiceType.inspection;
  }

  bool _submitting = false;
  bool _picking = false;
  bool _uploading = false;
  double _uploadProgress = 0;
  EvidenceDraft? _draft;
  CancelToken? _cancel;

  String _fileError(Object error) => switch (error) {
        EvidenceFailure(code: 'size') => journeyText(
            context,
            'Cada archivo debe tener entre 1 byte y 10 MB.',
            'Each file must be between 1 byte and 10 MB.',
            pt: 'Cada ficheiro deve ter entre 1 byte e 10 MB.'),
        EvidenceFailure(code: 'total') => journeyText(context,
            'El límite total es de 25 MB.', 'The combined limit is 25 MB.',
            pt: 'O limite total é de 25 MB.'),
        EvidenceFailure(code: 'count') => journeyText(
            context,
            'Puedes adjuntar hasta cinco archivos.',
            'You can attach up to five files.',
            pt: 'Pode anexar até cinco ficheiros.'),
        EvidenceFailure(code: 'type') => journeyText(
            context,
            'Selecciona un archivo JPG, PNG, PDF o CSV.',
            'Choose a JPG, PNG, PDF or CSV file.',
            pt: 'Escolha um ficheiro JPG, PNG, PDF ou CSV.'),
        EvidenceFailure(code: 'duplicate') => journeyText(
            context,
            'Ese archivo ya está seleccionado.',
            'That file is already selected.',
            pt: 'Esse ficheiro já está selecionado.'),
        _ => journeyText(
            context,
            'No se pudo completar la carga. Los archivos siguen seleccionados para reintentar. La solicitud no se ha enviado.',
            'Upload could not finish. Your selected files remain available to retry. The request has not been sent.',
            pt: 'Não foi possível concluir o envio dos ficheiros. A seleção continua disponível para tentar novamente. O pedido não foi enviado.'),
      };

  Future<void> _pick(bool photo) async {
    final assetId = _siteId;
    final workspace = ref.read(apiClientProvider).workspaceId;
    if (assetId == null || workspace == null) return;
    setState(() => _picking = true);
    try {
      final file = await ref.read(evidencePickerProvider).pick(photo: photo);
      if (!mounted || file == null) return;
      if (_siteId != assetId ||
          ref.read(apiClientProvider).workspaceId != workspace) {
        throw const EvidenceFailure('workspace');
      }
      final draft =
          _draft ?? EvidenceDraft(assetId: assetId, workspaceId: workspace);
      draft.add(file);
      setState(() => _draft = draft);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(_fileError(error))));
      }
    } finally {
      if (mounted) setState(() => _picking = false);
    }
  }

  @override
  void dispose() {
    _cancel?.cancel();
    _desc.dispose();
    super.dispose();
  }

  Future<void> _submit(List<CustomerAsset> sites) async {
    final site = sites.where((s) => s.id == _siteId).firstOrNull;
    if (site == null || _desc.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(journeyText(
              context,
              'Selecciona un activo y describe la solicitud.',
              'Select an asset and describe the request.',
              pt: 'Selecione um ativo e descreva o pedido.'))));
      return;
    }
    setState(() => _submitting = true);
    try {
      final draft = _draft;
      final references = <String>[];
      if (draft != null && draft.files.isNotEmpty) {
        if (draft.assetId != site.id) throw const EvidenceFailure('workspace');
        setState(() {
          _uploading = true;
          _uploadProgress = 0;
        });
        _cancel = CancelToken();
        references.addAll(await ref
            .read(evidenceRepositoryProvider)
            .upload(draft, cancel: _cancel!, onProgress: (value) {
          if (mounted) setState(() => _uploadProgress = value);
        }));
        if (!mounted) return;
        setState(() => _uploading = false);
      }
      final req = await ref.read(workRepositoryProvider).submit(
            type: _type,
            siteId: site.id,
            siteName: site.name,
            canonicalAsset: true,
            urgency: _urgency,
            description: _desc.text.trim(),
            attachments: references,
            attachmentFiles:
                draft?.files.map((file) => file.uploaded!).toList() ?? const [],
          );
      ref.invalidate(serviceRequestsProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(req.pendingSync
              ? journeyText(
                  context,
                  'Guardada en este dispositivo. Pendiente de confirmación del servidor.',
                  'Saved on this device. Waiting for server confirmation.',
                  pt:
                      'Guardado neste dispositivo. A aguardar confirmação do servidor.')
              : journeyText(context, 'Solicitud enviada.', 'Request submitted.',
                  pt: 'Pedido enviado.'))));
      context.go('/work/${req.id}');
    } catch (error) {
      if (!mounted) return;
      if (_uploading || error is EvidenceFailure) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(_fileError(error))));
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(journeyText(
              context,
              'No se pudo enviar. Comprueba el activo y tus permisos e inténtalo de nuevo.',
              'Could not submit. Check the asset and your permissions, then try again.',
              pt: 'Não foi possível enviar. Verifique o ativo e as suas permissões e tente novamente.'))));
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
          _uploading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final sitesAsync = ref.watch(customerAssetsProvider);
    final l10n = AppLocalizations.of(context);
    final demo = ref.watch(appConfigProvider).demoMode;
    ref.listen(customerExperienceProvider, (previous, next) {
      if (_draft != null &&
          next.hasValue &&
          next.value!.activeWorkspaceId != _draft!.workspaceId) {
        _cancel?.cancel();
        setState(() {
          _draft = null;
          _siteId = null;
        });
      }
    });
    return PopScope(
        canPop: !_submitting,
        child: Scaffold(
          appBar: AppBar(
              title: Text(journeyText(
                  context, 'Solicitar servicio', 'Request service',
                  pt: 'Pedir serviço'))),
          body: sitesAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('$e')),
            data: (env) {
              final sites = env.value;
              final selected =
                  sites.any((s) => s.id == _siteId) ? _siteId : null;
              return ListView(
                padding: const EdgeInsets.all(GvSpacing.lg),
                children: [
                  if (sites.isEmpty) ...[
                    Text(journeyText(
                        context,
                        'Añade el activo donde necesitas el servicio, o acepta la invitación si GeoVision ya lo ha creado.',
                        'Add the asset that needs this service, or accept your invitation if GeoVision has already created it.',
                        pt: 'Adicione o ativo que precisa deste serviço ou aceite o convite se a GeoVision já o criou.')),
                    TextButton(
                        onPressed: () => context.push('/assets/new'),
                        child: Text(journeyText(
                            context, 'Añadir activo', 'Add asset',
                            pt: 'Adicionar ativo'))),
                    TextButton(
                        onPressed: () => context.push('/invitation/accept'),
                        child: Text(journeyText(
                            context, 'Aceptar invitación', 'Accept invitation',
                            pt: 'Aceitar convite'))),
                  ],
                  if (_siteId != null && selected == null)
                    Text(journeyText(
                        context,
                        'El activo seleccionado ya no está disponible. Selecciona otro para continuar.',
                        'The selected asset is unavailable. Choose another to continue.',
                        pt: 'O ativo selecionado não está disponível. Escolha outro para continuar.')),
                  if (env.fromCache)
                    Text(journeyText(
                        context,
                        'Copia guardada: los permisos se comprobarán al enviar.',
                        'Cached copy: permissions will be checked when submitted.',
                        pt: 'Cópia guardada: as permissões serão verificadas no envio.')),
                  Text(
                      journeyText(context, 'Tipo de servicio', 'Service type',
                          pt: 'Tipo de serviço'),
                      style: const TextStyle(
                          color: GvColors.textSecondary, fontSize: 13)),
                  const SizedBox(height: GvSpacing.sm),
                  Wrap(
                    spacing: GvSpacing.sm,
                    children: ServiceType.values
                        .map((t) => ChoiceChip(
                              label: Text(
                                  journeyText(
                                      context,
                                      const [
                                        'Operación con dron',
                                        'Inspección',
                                        'Instalación de dispositivo',
                                        'Mantenimiento',
                                        'Informar de un problema'
                                      ][t.index],
                                      t.label,
                                      pt: const [
                                        'Operação com drone',
                                        'Inspeção',
                                        'Instalação de dispositivo',
                                        'Manutenção',
                                        'Comunicar um problema'
                                      ][t.index]),
                                  style: const TextStyle(fontSize: 12)),
                              selected: _type == t,
                              onSelected: _submitting
                                  ? null
                                  : (_) => setState(() => _type = t),
                              selectedColor:
                                  GvColors.accentCyan.withValues(alpha: 0.2),
                              backgroundColor: GvColors.surfaceDeep,
                              side: const BorderSide(color: GvColors.border),
                            ))
                        .toList(),
                  ),
                  const SizedBox(height: GvSpacing.lg),
                  Text(journeyText(context, 'Activo', 'Asset', pt: 'Ativo'),
                      style: const TextStyle(
                          color: GvColors.textSecondary, fontSize: 13)),
                  const SizedBox(height: GvSpacing.sm),
                  GvCard(
                    padding:
                        const EdgeInsets.symmetric(horizontal: GvSpacing.md),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        isExpanded: true,
                        value: selected,
                        hint: Text(journeyText(
                            context, 'Seleccionar activo', 'Select asset',
                            pt: 'Selecionar ativo')),
                        dropdownColor: GvColors.surface,
                        items: sites
                            .map((s) => DropdownMenuItem(
                                value: s.id, child: Text(s.name)))
                            .toList(),
                        onChanged: _submitting ||
                                _picking ||
                                (_draft?.files.isNotEmpty ?? false)
                            ? null
                            : (v) => setState(() {
                                  _siteId = v;
                                  _draft = null;
                                }),
                      ),
                    ),
                  ),
                  const SizedBox(height: GvSpacing.lg),
                  Text(
                      journeyText(context, 'Urgencia', 'Urgency',
                          pt: 'Urgência'),
                      style: const TextStyle(
                          color: GvColors.textSecondary, fontSize: 13)),
                  const SizedBox(height: GvSpacing.sm),
                  Wrap(
                    spacing: GvSpacing.sm,
                    children: ['low', 'normal', 'high', 'critical']
                        .map((u) => ChoiceChip(
                              label: Text(
                                  journeyText(
                                      context,
                                      const {
                                        'low': 'Baja',
                                        'normal': 'Normal',
                                        'high': 'Alta',
                                        'critical': 'Crítica'
                                      }[u]!,
                                      u,
                                      pt: const {
                                        'low': 'Baixa',
                                        'normal': 'Normal',
                                        'high': 'Alta',
                                        'critical': 'Crítica'
                                      }[u]!),
                                  style: const TextStyle(fontSize: 12)),
                              selected: _urgency == u,
                              onSelected: _submitting
                                  ? null
                                  : (_) => setState(() => _urgency = u),
                              selectedColor:
                                  GvColors.high.withValues(alpha: 0.2),
                              backgroundColor: GvColors.surfaceDeep,
                              side: const BorderSide(color: GvColors.border),
                            ))
                        .toList(),
                  ),
                  const SizedBox(height: GvSpacing.lg),
                  Text(
                      journeyText(context, 'Descripción', 'Description',
                          pt: 'Descrição'),
                      style: const TextStyle(
                          color: GvColors.textSecondary, fontSize: 13)),
                  const SizedBox(height: GvSpacing.sm),
                  TextField(
                    controller: _desc,
                    enabled: !_submitting,
                    maxLines: 4,
                    maxLength: 5000,
                    decoration: InputDecoration(hintText: l10n.describeNeed),
                  ),
                  const SizedBox(height: GvSpacing.md),
                  Text(journeyText(
                      context,
                      'Adjuntos opcionales: JPG, PNG, PDF o CSV. Máximo 5 archivos, 10 MB por archivo y 25 MB en total.',
                      'Optional evidence: JPG, PNG, PDF or CSV. Up to 5 files, 10 MB each and 25 MB combined.',
                      pt: 'Anexos opcionais: JPG, PNG, PDF ou CSV. Até 5 ficheiros, 10 MB por ficheiro e 25 MB no total.')),
                  if (demo)
                    Text(journeyText(
                        context,
                        'La carga de archivos requiere una cuenta conectada.',
                        'File upload requires a connected account.',
                        pt: 'O envio de ficheiros requer uma conta ligada.')),
                  if (selected == null)
                    Text(journeyText(context, 'Selecciona primero el activo.',
                        'Select the asset first.',
                        pt: 'Selecione primeiro o ativo.')),
                  Wrap(spacing: 8, children: [
                    OutlinedButton.icon(
                      onPressed:
                          demo || selected == null || _submitting || _picking
                              ? null
                              : () => _pick(false),
                      icon: const Icon(Icons.attach_file),
                      label: Text(journeyText(
                          context, 'Adjuntar archivo', 'Attach file',
                          pt: 'Anexar ficheiro')),
                    ),
                    OutlinedButton.icon(
                      onPressed:
                          demo || selected == null || _submitting || _picking
                              ? null
                              : () => _pick(true),
                      icon: const Icon(Icons.photo_library_outlined),
                      label: Text(journeyText(
                          context, 'Elegir foto', 'Choose photo',
                          pt: 'Escolher fotografia')),
                    ),
                  ]),
                  if (_picking) const LinearProgressIndicator(),
                  for (final file in _draft?.files ?? <SelectedEvidence>[])
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(file.filename,
                          maxLines: 2, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                          '${(file.bytes.length / 1024).toStringAsFixed(0)} KB · ${file.uploaded == null ? journeyText(context, 'Pendiente de subir', 'Waiting to upload', pt: 'A aguardar envio') : journeyText(context, 'Cargado', 'Uploaded', pt: 'Enviado')}'),
                      leading: Icon(file.uploaded == null
                          ? Icons.attach_file
                          : Icons.cloud_done_outlined),
                      trailing: IconButton(
                          tooltip: journeyText(context,
                              'Quitar de la solicitud', 'Remove from request',
                              pt: 'Retirar do pedido'),
                          onPressed: _submitting
                              ? null
                              : () =>
                                  setState(() => _draft!.files.remove(file)),
                          icon: const Icon(Icons.close)),
                    ),
                  if (_draft?.files.isNotEmpty ?? false)
                    Text(journeyText(
                        context,
                        'Los archivos se cargarán al enviar. Al salir se borran las selecciones. Para cambiar de activo, quita primero los adjuntos.',
                        'Files upload when you submit. Leaving this form clears your selections. To change asset, remove the attachments first.',
                        pt: 'Os ficheiros são carregados ao enviar o pedido. Sair deste formulário elimina a seleção. Para mudar de ativo, retire primeiro os anexos.')),
                  if (_uploading) ...[
                    LinearProgressIndicator(value: _uploadProgress),
                    Text(journeyText(
                        context, 'Cargando archivos…', 'Uploading files…',
                        pt: 'A enviar ficheiros…')),
                    TextButton(
                        onPressed: () => _cancel?.cancel(),
                        child: Text(journeyText(
                            context, 'Cancelar carga', 'Cancel upload',
                            pt: 'Cancelar envio'))),
                  ],
                  const SizedBox(height: GvSpacing.xl),
                  FilledButton(
                    onPressed: _submitting || _picking || sites.isEmpty
                        ? null
                        : () => _submit(sites),
                    child: _submitting
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : Text(journeyText(
                            context, 'Enviar solicitud', 'Submit request',
                            pt: 'Enviar pedido')),
                  ),
                ],
              );
            },
          ),
        ));
  }
}
