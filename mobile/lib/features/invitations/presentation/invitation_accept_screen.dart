import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/routing/customer_routes.dart';
import '../../account/data/customer_experience_repository.dart';
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
    await result.when<Future<void>>(
      ok: (destination) async {
        final path = CustomerRoutes.forInvitation(
          kind: destination.kind,
          targetId: destination.targetId,
          path: destination.path,
        );
        if (path == null) {
          setState(() {
            _error = 'This invitation destination is not supported.';
            _loading = false;
          });
          return;
        }
        if (destination.workspaceId.isNotEmpty) {
          try {
            await ref.read(customerExperienceProvider.future);
          } catch (_) {
            // The explicit selection below performs the authoritative check.
          }
          final switched = await ref
              .read(customerExperienceProvider.notifier)
              .switchWorkspace(destination.workspaceId);
          if (!switched) {
            if (!mounted) return;
            setState(() {
              _error = 'The invited workspace could not be opened.';
              _loading = false;
            });
            return;
          }
        }
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invitation accepted.')),
        );
        context.go(path);
      },
      err: (failure) async {
        setState(() {
          _error = failure.message;
          _loading = false;
        });
      },
    );
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
