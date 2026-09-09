import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../data/invitations_repository.dart';
import '../domain/invitation.dart';

class InvitationAcceptScreen extends ConsumerStatefulWidget {
  const InvitationAcceptScreen({super.key, this.initialToken});

  final String? initialToken;

  @override
  ConsumerState<InvitationAcceptScreen> createState() =>
      _InvitationAcceptScreenState();
}

class _InvitationAcceptScreenState
    extends ConsumerState<InvitationAcceptScreen> {
  late final TextEditingController _token;
  InvitationPreview? _preview;
  String? _error;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _token = TextEditingController(text: widget.initialToken ?? '');
    if (_token.text.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _loadPreview());
    }
  }

  @override
  void dispose() {
    _token.dispose();
    super.dispose();
  }

  Future<void> _loadPreview() async {
    if (_token.text.trim().isEmpty) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    final result = await ref
        .read(invitationsRepositoryProvider)
        .preview(_token.text.trim());
    if (!mounted) return;
    result.when(
      ok: (value) => setState(() {
        _preview = value;
        _loading = false;
      }),
      err: (failure) => setState(() {
        _error = failure.message;
        _loading = false;
      }),
    );
  }

  Future<void> _accept() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final result = await ref
        .read(invitationsRepositoryProvider)
        .accept(_token.text.trim());
    if (!mounted) return;
    result.when(
      ok: (destination) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invitation accepted.')),
        );
        context.go(_mobilePath(destination));
      },
      err: (failure) => setState(() {
        _error = failure.message;
        _loading = false;
      }),
    );
  }

  String _mobilePath(InvitationDestination destination) {
    switch (destination.kind) {
      case 'order':
        return destination.targetId == null
            ? '/orders'
            : '/orders/${destination.targetId}';
      case 'service_result':
        return '/work';
      case 'report':
        return '/reports';
      case 'asset':
        // Generic Asset detail is introduced with the unified asset UI. Until
        // then the sites view is the safe cross-sector landing surface.
        return '/sites';
      default:
        return '/portal';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GvColors.bgDarker,
      appBar: AppBar(title: const Text('Invitation')),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 520),
              child: GvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text('Join existing work',
                        style: TextStyle(
                            fontSize: 24, fontWeight: FontWeight.w800)),
                    const SizedBox(height: GvSpacing.xs),
                    const Text(
                      'Sign in with the invited email. GeoVision will open the existing asset or result without creating another copy.',
                      style: TextStyle(color: GvColors.textSecondary),
                    ),
                    const SizedBox(height: GvSpacing.lg),
                    TextField(
                      controller: _token,
                      obscureText: true,
                      autocorrect: false,
                      enableSuggestions: false,
                      decoration: const InputDecoration(
                        labelText: 'Secure invitation code',
                        prefixIcon: Icon(Icons.key_outlined),
                      ),
                      onSubmitted: (_) => _loadPreview(),
                    ),
                    if (_preview case final preview?) ...[
                      const SizedBox(height: GvSpacing.lg),
                      Text(preview.organizationName,
                          style: const TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w700)),
                      Text('${preview.workspaceName} · ${preview.emailHint}',
                          style:
                              const TextStyle(color: GvColors.textSecondary)),
                      Text('Access: ${preview.role} · ${preview.targetKind}',
                          style: const TextStyle(color: GvColors.accentCyan)),
                    ],
                    if (_error != null) ...[
                      const SizedBox(height: GvSpacing.md),
                      Text(_error!,
                          style: const TextStyle(color: GvColors.critical)),
                    ],
                    const SizedBox(height: GvSpacing.lg),
                    if (_preview == null)
                      FilledButton(
                        onPressed: _loading ? null : _loadPreview,
                        child: _loading
                            ? const SizedBox.square(
                                dimension: 18,
                                child:
                                    CircularProgressIndicator(strokeWidth: 2))
                            : const Text('View invitation'),
                      )
                    else
                      FilledButton.icon(
                        onPressed: _loading ? null : _accept,
                        icon: const Icon(Icons.check_circle_outline),
                        label: const Text('Accept and open'),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
