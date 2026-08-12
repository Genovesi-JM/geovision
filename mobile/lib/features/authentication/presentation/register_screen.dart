import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../account/domain/account_profile.dart';
import '../domain/registration_request.dart';
import 'auth_controller.dart';
import 'registration_copy.dart';

class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _identityKey = GlobalKey<FormState>();
  final _securityKey = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  final _organisation = TextEditingController();

  int _step = 0;
  bool _loading = false;
  bool _obscure = true;
  String? _error;
  AccountProfileDefinition _profile = AccountProfiles.public[1];
  late Set<String> _sectors;
  late Set<String> _useCases;

  @override
  void initState() {
    super.initState();
    _sectors = {_profile.defaultSector};
    _useCases = {..._profile.defaultUseCases};
  }

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    _confirm.dispose();
    _organisation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final copy = RegistrationCopy.of(context);
    return Scaffold(
      backgroundColor: GvColors.bgDarker,
      appBar: AppBar(
        leading: IconButton(
          onPressed: _step == 0
              ? () => context.go('/login')
              : () => setState(() => _step--),
          icon: const Icon(Icons.arrow_back),
        ),
        title: Text(copy.createAccount),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(copy.title,
                      style: const TextStyle(
                          fontSize: 25,
                          fontWeight: FontWeight.w800,
                          color: GvColors.textPrimary)),
                  const SizedBox(height: 6),
                  Text(copy.subtitle,
                      style: const TextStyle(color: GvColors.textSecondary)),
                  const SizedBox(height: GvSpacing.lg),
                  Row(
                    children: List.generate(
                        3,
                        (index) => Expanded(
                              child: Container(
                                height: 5,
                                margin:
                                    EdgeInsets.only(right: index == 2 ? 0 : 7),
                                decoration: BoxDecoration(
                                  color: index <= _step
                                      ? GvColors.accentGreen
                                      : GvColors.borderStrong,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                            )),
                  ),
                  const SizedBox(height: GvSpacing.sm),
                  Text(
                      '${_step + 1}/3 · ${[
                        copy.stepIdentity,
                        copy.stepSecurity,
                        copy.stepProfile
                      ][_step]}',
                      style: const TextStyle(
                          color: GvColors.accentCyan,
                          fontWeight: FontWeight.w700)),
                  const SizedBox(height: GvSpacing.lg),
                  GvCard(
                      child: AnimatedSwitcher(
                    duration: const Duration(milliseconds: 180),
                    child: switch (_step) {
                      0 => _identityStep(copy),
                      1 => _securityStep(copy),
                      _ => _profileStep(copy),
                    },
                  )),
                  if (_error != null) ...[
                    const SizedBox(height: GvSpacing.md),
                    Text(_error!,
                        style: const TextStyle(color: GvColors.critical)),
                  ],
                  const SizedBox(height: GvSpacing.lg),
                  Row(children: [
                    if (_step > 0) ...[
                      Expanded(
                          child: OutlinedButton(
                        onPressed:
                            _loading ? null : () => setState(() => _step--),
                        child: Text(copy.back),
                      )),
                      const SizedBox(width: GvSpacing.sm),
                    ],
                    Expanded(
                        flex: 2,
                        child: FilledButton(
                          onPressed: _loading ? null : () => _advance(copy),
                          child: _loading
                              ? const SizedBox.square(
                                  dimension: 18,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2))
                              : Text(_step == 2 ? copy.finish : copy.next),
                        )),
                  ]),
                  const SizedBox(height: GvSpacing.sm),
                  TextButton(
                    onPressed: _loading ? null : () => context.go('/login'),
                    child: Text(copy.alreadyHaveAccount),
                  ),
                  Text(copy.privacy,
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                          color: GvColors.textMuted, fontSize: 11)),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _identityStep(RegistrationCopy copy) => Form(
        key: _identityKey,
        child: Column(children: [
          TextFormField(
            controller: _name,
            textInputAction: TextInputAction.next,
            decoration: InputDecoration(
                labelText: copy.fullName,
                prefixIcon: const Icon(Icons.person_outline)),
            validator: (value) =>
                (value?.trim().length ?? 0) < 2 ? copy.requiredField : null,
          ),
          const SizedBox(height: GvSpacing.md),
          TextFormField(
            controller: _email,
            keyboardType: TextInputType.emailAddress,
            autofillHints: const [AutofillHints.email],
            decoration: const InputDecoration(
                labelText: 'Email', prefixIcon: Icon(Icons.mail_outline)),
            validator: (value) => value == null ||
                    !RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
                        .hasMatch(value.trim())
                ? copy.invalidEmail
                : null,
          ),
        ]),
      );

  Widget _securityStep(RegistrationCopy copy) => Form(
        key: _securityKey,
        child: Column(children: [
          TextFormField(
            controller: _password,
            obscureText: _obscure,
            autofillHints: const [AutofillHints.newPassword],
            decoration: InputDecoration(
              labelText: copy.passwordHelp,
              prefixIcon: const Icon(Icons.lock_outline),
              suffixIcon: IconButton(
                onPressed: () => setState(() => _obscure = !_obscure),
                icon: Icon(_obscure ? Icons.visibility_off : Icons.visibility),
              ),
            ),
            validator: (value) =>
                (value?.length ?? 0) < 8 ? copy.passwordHelp : null,
          ),
          const SizedBox(height: GvSpacing.md),
          TextFormField(
            controller: _confirm,
            obscureText: _obscure,
            decoration: InputDecoration(
                labelText: copy.confirmPassword,
                prefixIcon: const Icon(Icons.lock_reset)),
            validator: (value) =>
                value != _password.text ? copy.passwordMismatch : null,
          ),
        ]),
      );

  Widget _profileStep(RegistrationCopy copy) => Column(
        key: ValueKey(_profile.id),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(copy.chooseProfile,
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: GvSpacing.sm),
          DropdownButtonFormField<AccountProfileDefinition>(
            initialValue: _profile,
            isExpanded: true,
            items: AccountProfiles.public
                .map((profile) => DropdownMenuItem(
                    value: profile, child: Text(copy.profile(profile.id))))
                .toList(),
            onChanged: (value) {
              if (value == null) return;
              setState(() {
                _profile = value;
                _sectors = {value.defaultSector};
                _useCases = {...value.defaultUseCases};
              });
            },
          ),
          if (_profile.isCompany) ...[
            const SizedBox(height: GvSpacing.md),
            TextField(
              controller: _organisation,
              decoration: InputDecoration(
                  labelText: copy.organisation,
                  prefixIcon: const Icon(Icons.business_outlined)),
            ),
          ],
          const SizedBox(height: GvSpacing.lg),
          Text(copy.chooseSectors,
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: GvSpacing.xs),
          Wrap(
              spacing: 7,
              runSpacing: 7,
              children: _profile.allowedSectors
                  .map((id) => FilterChip(
                        label: Text(copy.sector(id)),
                        selected: _sectors.contains(id),
                        onSelected: (selected) => setState(() {
                          if (selected) {
                            _sectors.add(id);
                          } else if (_sectors.length > 1) {
                            _sectors.remove(id);
                          }
                        }),
                      ))
                  .toList()),
          const SizedBox(height: GvSpacing.lg),
          Text(copy.chooseGoals,
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: GvSpacing.xs),
          Wrap(
              spacing: 7,
              runSpacing: 7,
              children: _profile.allowedUseCases
                  .map((id) => FilterChip(
                        label: Text(copy.useCase(id)),
                        selected: _useCases.contains(id),
                        onSelected: (selected) => setState(() {
                          if (selected) {
                            _useCases.add(id);
                          } else if (_useCases.length > 1) {
                            _useCases.remove(id);
                          }
                        }),
                      ))
                  .toList()),
        ],
      );

  Future<void> _advance(RegistrationCopy copy) async {
    FocusScope.of(context).unfocus();
    setState(() => _error = null);
    if (_step == 0) {
      if (_identityKey.currentState?.validate() != true) return;
      setState(() => _step = 1);
      return;
    }
    if (_step == 1) {
      if (_securityKey.currentState?.validate() != true) return;
      setState(() => _step = 2);
      return;
    }
    setState(() => _loading = true);
    final result = await ref.read(authControllerProvider.notifier).register(
          RegistrationRequest(
            email: _email.text,
            password: _password.text,
            fullName: _name.text,
            customerType: _profile.id,
            sectors: _sectors.toList(),
            useCases: _useCases.toList(),
            organisation: _organisation.text,
          ),
        );
    if (!mounted) return;
    setState(() => _loading = false);
    result.when(
      ok: (_) => context.go('/portal'),
      err: (failure) => setState(() => _error = failure.message),
    );
  }
}
