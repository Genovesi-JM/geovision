import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../sites/data/sites_repository.dart';
import '../data/work_repository.dart';
import '../domain/service_request.dart';

class NewRequestScreen extends ConsumerStatefulWidget {
  const NewRequestScreen({super.key});
  @override
  ConsumerState<NewRequestScreen> createState() => _NewRequestScreenState();
}

class _NewRequestScreenState extends ConsumerState<NewRequestScreen> {
  ServiceType _type = ServiceType.inspection;
  String _urgency = 'normal';
  String? _siteId;
  final _desc = TextEditingController();
  final _attachments = <String>[];
  bool _submitting = false;

  @override
  void dispose() {
    _desc.dispose();
    super.dispose();
  }

  Future<void> _submit(List<dynamic> sites) async {
    if (_siteId == null || _desc.text.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Select a site and describe the request.')));
      return;
    }
    setState(() => _submitting = true);
    final site = sites.firstWhere((s) => s.id == _siteId);
    final req = await ref.read(workRepositoryProvider).submit(
          type: _type,
          siteId: _siteId!,
          siteName: site.name as String,
          urgency: _urgency,
          description: _desc.text.trim(),
          attachments: _attachments,
        );
    ref.invalidate(serviceRequestsProvider);
    if (!mounted) return;
    setState(() => _submitting = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(req.pendingSync
          ? 'Saved offline — will sync when back online.'
          : 'Request submitted.'),
    ));
    context.go('/work');
  }

  @override
  Widget build(BuildContext context) {
    final sitesAsync = ref.watch(sitesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('New request')),
      body: sitesAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('$e')),
        data: (env) {
          final sites = env.value;
          _siteId ??= sites.isNotEmpty ? sites.first.id : null;
          return ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              const Text('Service type',
                  style:
                      TextStyle(color: GvColors.textSecondary, fontSize: 13)),
              const SizedBox(height: GvSpacing.sm),
              Wrap(
                spacing: GvSpacing.sm,
                children: ServiceType.values
                    .map((t) => ChoiceChip(
                          label: Text(t.label,
                              style: const TextStyle(fontSize: 12)),
                          selected: _type == t,
                          onSelected: (_) => setState(() => _type = t),
                          selectedColor:
                              GvColors.accentCyan.withValues(alpha: 0.2),
                          backgroundColor: GvColors.surfaceDeep,
                          side: const BorderSide(color: GvColors.border),
                        ))
                    .toList(),
              ),
              const SizedBox(height: GvSpacing.lg),
              const Text('Site',
                  style:
                      TextStyle(color: GvColors.textSecondary, fontSize: 13)),
              const SizedBox(height: GvSpacing.sm),
              GvCard(
                padding: const EdgeInsets.symmetric(horizontal: GvSpacing.md),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String>(
                    isExpanded: true,
                    value: _siteId,
                    dropdownColor: GvColors.surface,
                    items: sites
                        .map((s) =>
                            DropdownMenuItem(value: s.id, child: Text(s.name)))
                        .toList(),
                    onChanged: (v) => setState(() => _siteId = v),
                  ),
                ),
              ),
              const SizedBox(height: GvSpacing.lg),
              const Text('Urgency',
                  style:
                      TextStyle(color: GvColors.textSecondary, fontSize: 13)),
              const SizedBox(height: GvSpacing.sm),
              Wrap(
                spacing: GvSpacing.sm,
                children: ['low', 'normal', 'high', 'critical']
                    .map((u) => ChoiceChip(
                          label: Text(u, style: const TextStyle(fontSize: 12)),
                          selected: _urgency == u,
                          onSelected: (_) => setState(() => _urgency = u),
                          selectedColor: GvColors.high.withValues(alpha: 0.2),
                          backgroundColor: GvColors.surfaceDeep,
                          side: const BorderSide(color: GvColors.border),
                        ))
                    .toList(),
              ),
              const SizedBox(height: GvSpacing.lg),
              const Text('Description',
                  style:
                      TextStyle(color: GvColors.textSecondary, fontSize: 13)),
              const SizedBox(height: GvSpacing.sm),
              TextField(
                controller: _desc,
                maxLines: 4,
                decoration:
                    const InputDecoration(hintText: 'Describe what you need…'),
              ),
              const SizedBox(height: GvSpacing.md),
              OutlinedButton.icon(
                onPressed: () => setState(() => _attachments
                    .add('evidence_${_attachments.length + 1}.jpg')),
                icon: const Icon(Icons.attach_file),
                label: Text(_attachments.isEmpty
                    ? 'Attach evidence (photo/file)'
                    : '${_attachments.length} attachment(s)'),
              ),
              const SizedBox(height: GvSpacing.xl),
              FilledButton(
                onPressed: _submitting ? null : () => _submit(sites),
                child: _submitting
                    ? const SizedBox(
                        height: 18,
                        width: 18,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Submit request'),
              ),
            ],
          );
        },
      ),
    );
  }
}
