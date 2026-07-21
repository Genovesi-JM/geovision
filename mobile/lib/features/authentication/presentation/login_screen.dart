import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import 'auth_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});
  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _loading = false;
  String? _error;
  bool _obscure = true;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    final res = await ref
        .read(authControllerProvider.notifier)
        .login(_email.text, _password.text);
    if (!mounted) return;
    setState(() => _loading = false);
    res.when(
      ok: (_) => context.go('/home'),
      err: (f) => setState(() => _error = f.message),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: GvColors.bgDarker,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(GvSpacing.xl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Container(
                    width: 64,
                    height: 64,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      gradient: GvColors.gradientAccent,
                      borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
                    ),
                    child: const Icon(Icons.satellite_alt,
                        color: GvColors.bgDarker, size: 34),
                  ),
                  const SizedBox(height: GvSpacing.lg),
                  const Text('GeoVision',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          color: GvColors.textPrimary)),
                  const SizedBox(height: 4),
                  const Text('Operational platform',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: GvColors.textSecondary)),
                  const SizedBox(height: GvSpacing.xl),
                  GvCard(
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          TextFormField(
                            controller: _email,
                            keyboardType: TextInputType.emailAddress,
                            autofillHints: const [AutofillHints.email],
                            decoration: const InputDecoration(
                                hintText: 'Email',
                                prefixIcon: Icon(Icons.mail_outline)),
                            validator: (v) => (v == null || !v.contains('@'))
                                ? 'Enter a valid email'
                                : null,
                          ),
                          const SizedBox(height: GvSpacing.md),
                          TextFormField(
                            controller: _password,
                            obscureText: _obscure,
                            decoration: InputDecoration(
                              hintText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline),
                              suffixIcon: IconButton(
                                icon: Icon(_obscure
                                    ? Icons.visibility_off
                                    : Icons.visibility),
                                onPressed: () =>
                                    setState(() => _obscure = !_obscure),
                              ),
                            ),
                            validator: (v) => (v == null || v.length < 4)
                                ? 'Enter your password'
                                : null,
                          ),
                          if (_error != null) ...[
                            const SizedBox(height: GvSpacing.md),
                            Text(_error!,
                                style: const TextStyle(
                                    color: GvColors.critical, fontSize: 13)),
                          ],
                          const SizedBox(height: GvSpacing.lg),
                          FilledButton(
                            onPressed: _loading ? null : _submit,
                            child: _loading
                                ? const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2))
                                : const Text('Sign in'),
                          ),
                          TextButton(
                            onPressed: () => _showForgot(context),
                            child: const Text('Forgot password?'),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: GvSpacing.lg),
                  OutlinedButton.icon(
                    onPressed: () {
                      ref.read(authControllerProvider.notifier).enterDemo();
                      context.go('/home');
                    },
                    icon: const Icon(Icons.play_circle_outline),
                    label: const Text('Explore demo'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _showForgot(BuildContext context) {
    final emailCtl = TextEditingController(text: _email.text);
    showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reset password'),
        content: TextField(
          controller: emailCtl,
          decoration: const InputDecoration(hintText: 'Email'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () async {
              await ref
                  .read(authRepositoryProvider)
                  .forgotPassword(emailCtl.text);
              if (ctx.mounted) Navigator.pop(ctx);
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                      content:
                          Text('If the email exists, a reset link was sent.')),
                );
              }
            },
            child: const Text('Send'),
          ),
        ],
      ),
    );
  }
}
