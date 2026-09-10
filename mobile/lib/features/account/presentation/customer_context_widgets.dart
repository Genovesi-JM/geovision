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
        label: 'Loading workspace',
        liveRegion: true,
        child: const LinearProgressIndicator(minHeight: 2),
      ),
      error: (_, __) => Material(
        color: GvColors.surfaceDeep,
        child: Semantics(
          button: true,
          label: 'Workspace unavailable. Retry.',
          child: InkWell(
            onTap: () => ref.read(customerExperienceProvider.notifier).reload(),
            child: const Padding(
              padding: EdgeInsets.symmetric(
                  horizontal: GvSpacing.lg, vertical: GvSpacing.sm),
              child: Row(children: [
                Icon(Icons.sync_problem, size: 17, color: GvColors.high),
                SizedBox(width: GvSpacing.sm),
                Expanded(child: Text('Workspace unavailable · Tap to retry')),
              ]),
            ),
          ),
        ),
      ),
      data: (data) {
        final active = data.activeWorkspace;
        if (active == null) {
          return const Material(
            color: GvColors.surfaceDeep,
            child: Padding(
              padding: EdgeInsets.symmetric(
                  horizontal: GvSpacing.lg, vertical: GvSpacing.sm),
              child: Text('No customer workspace is available.'),
            ),
          );
        }
        final switchable = data.workspaces.length > 1;
        return Material(
          color: GvColors.surfaceDeep,
          child: Semantics(
            button: switchable,
            label: switchable
                ? 'Current workspace ${active.name}. Switch workspace.'
                : 'Current workspace ${active.name}.',
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
            const Text('Switch workspace',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
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
        const SnackBar(content: Text('Workspace could not be changed.')),
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
          body: const GvLoading(label: 'Loading workspace access…')),
      error: (_, __) => Scaffold(
        appBar: AppBar(title: Text(title)),
        body: GvErrorState(
          message: 'Workspace access could not be loaded.',
          onRetry: () => ref.read(customerExperienceProvider.notifier).reload(),
        ),
      ),
      data: (data) => data.hasCapability(capability)
          ? child
          : Scaffold(
              appBar: AppBar(title: Text(title)),
              body: GvEmpty(
                icon: Icons.lock_outline,
                message:
                    '$title is not enabled for this workspace. Ask a workspace administrator if you need access.',
              ),
            ),
    );
  }
}
