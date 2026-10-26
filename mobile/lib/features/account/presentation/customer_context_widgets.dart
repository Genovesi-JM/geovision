import '../../../core/localization/journey_copy.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/customer_experience_repository.dart';
import '../domain/customer_experience.dart';

class CustomerWorkspaceBar extends ConsumerWidget {
  const CustomerWorkspaceBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final experience = ref.watch(customerExperienceProvider);
    return experience.when(
      loading: () => Semantics(
        label: journeyText(
            context, 'Cargando el espacio de trabajo', 'Loading workspace',
            pt: 'A carregar o espaço de trabalho'),
        liveRegion: true,
        child: const LinearProgressIndicator(minHeight: 2),
      ),
      error: (_, __) => Material(
        color: GvColors.surfaceDeep,
        child: Semantics(
          button: true,
          label: journeyText(
              context,
              'Espacio de trabajo no disponible. Reintentar.',
              'Workspace unavailable. Retry.',
              pt: 'Espaço de trabalho indisponível. Tente novamente.'),
          child: InkWell(
            onTap: () => ref.read(customerExperienceProvider.notifier).reload(),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                  horizontal: GvSpacing.lg, vertical: GvSpacing.sm),
              child: Row(children: [
                const Icon(Icons.sync_problem, size: 17, color: GvColors.high),
                const SizedBox(width: GvSpacing.sm),
                Expanded(
                    child: Text(journeyText(
                        context,
                        'Espacio no disponible · Toca para reintentar',
                        'Workspace unavailable · Tap to retry',
                        pt: 'Espaço indisponível · Toque para tentar novamente'))),
              ]),
            ),
          ),
        ),
      ),
      data: (data) {
        final active = data.activeWorkspace;
        if (active == null) {
          return Material(
            color: GvColors.surfaceDeep,
            child: Padding(
              padding: const EdgeInsets.symmetric(
                  horizontal: GvSpacing.lg, vertical: GvSpacing.sm),
              child: Text(journeyText(
                  context,
                  'No hay un espacio de trabajo disponible.',
                  'No customer workspace is available.',
                  pt: 'Nenhum espaço de trabalho disponível.')),
            ),
          );
        }
        final switchable = data.workspaces.length > 1;
        return Material(
          color: GvColors.surfaceDeep,
          child: Semantics(
            button: switchable,
            label: switchable
                ? journeyText(
                    context,
                    'Espacio actual ${active.name}. Cambiar espacio.',
                    'Current workspace ${active.name}. Switch workspace.',
                    pt: 'Espaço atual ${active.name}. Mudar de espaço.')
                : journeyText(context, 'Espacio actual ${active.name}.',
                    'Current workspace ${active.name}.',
                    pt: 'Espaço atual ${active.name}.'),
            child: InkWell(
              onTap: switchable
                  ? () => _chooseWorkspace(
                      context, ref, data.workspaces, data.activeWorkspaceId)
                  : null,
              child: Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: GvSpacing.lg, vertical: GvSpacing.sm),
                child: Row(children: [
                  const Icon(Icons.business_outlined,
                      size: 17, color: GvColors.accentCyan),
                  const SizedBox(width: GvSpacing.sm),
                  Expanded(
                    child: Text(
                      active.organizationName.isEmpty
                          ? active.name
                          : '${active.organizationName} · ${active.name}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                  if (switchable)
                    const Icon(Icons.unfold_more,
                        size: 17, color: GvColors.textMuted),
                ]),
              ),
            ),
          ),
        );
      },
    );
  }

  Future<void> _chooseWorkspace(
    BuildContext context,
    WidgetRef ref,
    List<CustomerWorkspace> workspaces,
    String? activeId,
  ) async {
    final selected = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
                journeyText(
                    context, 'Cambiar espacio de trabajo', 'Switch workspace',
                    pt: 'Mudar de espaço de trabalho'),
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: GvSpacing.sm),
            for (final workspace in workspaces)
              ListTile(
                title: Text(workspace.name),
                subtitle:
                    Text('${workspace.organizationName} · ${workspace.role}'),
                trailing: workspace.id == activeId
                    ? const Icon(Icons.check_circle,
                        color: GvColors.accentGreen)
                    : null,
                onTap: () => Navigator.pop(sheetContext, workspace.id),
              ),
          ],
        ),
      ),
    );
    if (selected == null || !context.mounted) return;
    final switched = await ref
        .read(customerExperienceProvider.notifier)
        .switchWorkspace(selected);
    if (!switched && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(journeyText(context, 'No se pudo cambiar de espacio.',
                'Workspace could not be changed.',
                pt: 'Não foi possível mudar de espaço.'))),
      );
    }
  }
}

class CustomerCapabilityPage extends ConsumerWidget {
  const CustomerCapabilityPage({
    super.key,
    required this.capability,
    required this.title,
    required this.child,
  });

  final String capability;
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final experience = ref.watch(customerExperienceProvider);
    return experience.when(
      loading: () => Scaffold(
          appBar: AppBar(title: Text(title)),
          body: GvLoading(
              label: journeyText(context, 'Comprobando el acceso…',
                  'Loading workspace access…',
                  pt: 'A verificar o acesso…'))),
      error: (_, __) => Scaffold(
        appBar: AppBar(title: Text(title)),
        body: GvErrorState(
          message: journeyText(context, 'No se pudo comprobar el acceso.',
              'Workspace access could not be loaded.',
              pt: 'Não foi possível verificar o acesso.'),
          onRetry: () => ref.read(customerExperienceProvider.notifier).reload(),
        ),
      ),
      data: (data) => data.hasCapability(capability)
          ? child
          : Scaffold(
              appBar: AppBar(title: Text(title)),
              body: GvEmpty(
                icon: Icons.lock_outline,
                message: journeyText(
                    context,
                    'Esta función no está disponible en este espacio. Contacta con un administrador si necesitas acceso.',
                    '$title is not enabled for this workspace. Ask a workspace administrator if you need access.',
                    pt: 'Esta função não está disponível neste espaço. Contacte um administrador se precisar de acesso.'),
              ),
            ),
    );
  }
}
