import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_flavor.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_section_header.dart';
import '../../authentication/presentation/auth_controller.dart';
import '../../../l10n/app_localizations.dart';
import '../../authentication/presentation/registration_copy.dart';

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(authControllerProvider);
    final config = ref.watch(appConfigProvider);
    final profile = session.profile;
    final language = ref.watch(localeProvider).languageCode.toUpperCase();
    final text = AppLocalizations.of(context);
    final accountCopy = RegistrationCopy.of(context);

    return Scaffold(
      appBar: AppBar(title: Text(text.navMore)),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          GvCard(
            child: Row(
              children: [
                CircleAvatar(
                  radius: 26,
                  backgroundColor: GvColors.accentCyan.withValues(alpha: 0.2),
                  child: Text(
                    (profile?.displayName ?? 'G').substring(0, 1).toUpperCase(),
                    style: const TextStyle(
                        color: GvColors.accentCyan,
                        fontWeight: FontWeight.w800,
                        fontSize: 20),
                  ),
                ),
                const SizedBox(width: GvSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(profile?.displayName ?? 'Guest',
                          style: const TextStyle(
                              fontSize: 16, fontWeight: FontWeight.w800)),
                      Text(profile?.email ?? '',
                          style: const TextStyle(
                              color: GvColors.textMuted, fontSize: 12)),
                      if (profile?.organisation != null)
                        Text(profile!.organisation!,
                            style: const TextStyle(
                                color: GvColors.accentCyan, fontSize: 12)),
                    ],
                  ),
                ),
                if (session.isDemo)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: GvColors.accentBlue.withValues(alpha: 0.16),
                      borderRadius: BorderRadius.circular(GvSpacing.radiusPill),
                    ),
                    child: const Text('DEMO',
                        style: TextStyle(
                            color: GvColors.accentBlue,
                            fontSize: 10,
                            fontWeight: FontWeight.w800)),
                  ),
              ],
            ),
          ),
          if (profile != null) ...[
            const SizedBox(height: GvSpacing.md),
            GvCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(accountCopy.profile(profile.customerType),
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: GvSpacing.sm),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: profile.sectors
                        .map((sector) => Chip(
                            label: Text(accountCopy.sector(sector)),
                            visualDensity: VisualDensity.compact))
                        .toList(),
                  ),
                  if (profile.useCases.isNotEmpty) ...[
                    const SizedBox(height: GvSpacing.xs),
                    Text(profile.useCases.map(accountCopy.useCase).join(' · '),
                        style: const TextStyle(
                            color: GvColors.textSecondary, fontSize: 12)),
                  ],
                ],
              ),
            ),
          ],
          const SizedBox(height: GvSpacing.md),
          FilledButton.icon(
            onPressed: () => context.go('/account-live'),
            icon: const Icon(Icons.podcasts),
            label: Text(text.liveAccount),
          ),
          const SizedBox(height: GvSpacing.md),
          GvSectionHeader(title: text.operationsTools),
          _Group(children: [
            _Tile(
                icon: Icons.add_task_outlined,
                label: text.requestService,
                onTap: () => context.go('/work')),
            _Tile(
                icon: Icons.notifications_outlined,
                label: text.notificationSettings,
                onTap: () {}),
            _Tile(
                icon: Icons.description_outlined,
                label: text.reports,
                onTap: () => context.go('/reports')),
            _Tile(
                icon: Icons.shopping_bag_outlined,
                label: text.storeOrdersPayments,
                onTap: () => context.go('/orders')),
            _Tile(
                icon: Icons.payments_outlined,
                label: text.paymentMethods,
                onTap: () => context.go('/payment-methods')),
            _Tile(
                icon: Icons.sensors,
                label: text.devices,
                onTap: () => context.go('/devices')),
            _Tile(
                icon: Icons.menu_book_outlined,
                label: text.visualGuides,
                onTap: () => context.go('/guides')),
            _Tile(
                icon: Icons.language,
                label: '${text.language} ($language)',
                onTap: () => _selectLanguage(context, ref)),
          ]),
          const SizedBox(height: GvSpacing.md),
          GvSectionHeader(title: text.helpAndSettings),
          _Group(children: [
            _Tile(
                icon: Icons.auto_awesome,
                label: text.gaiaAssistant,
                onTap: () => context.go('/assistant')),
            _Tile(icon: Icons.security, label: text.security, onTap: () {}),
            _Tile(
                icon: Icons.privacy_tip_outlined,
                label: text.privacy,
                onTap: () {}),
            _Tile(icon: Icons.gavel_outlined, label: text.terms, onTap: () {}),
            _Tile(
                icon: Icons.support_agent,
                label: text.contactSupport,
                onTap: () => context.go('/support')),
          ]),
          const SizedBox(height: GvSpacing.md),
          if (session.isDemo)
            FilledButton.icon(
              onPressed: () => context.go('/login'),
              icon: const Icon(Icons.login),
              label: Text(text.signInToAccount),
            )
          else
            OutlinedButton.icon(
              onPressed: () async {
                await ref.read(authControllerProvider.notifier).logout();
                if (context.mounted) context.go('/login');
              },
              icon: const Icon(Icons.logout),
              label: Text(text.signOut),
            ),
          const SizedBox(height: GvSpacing.lg),
          Center(
            child: Text(
                'GeoVision · v0.1.0 · ${config.flavor.label}${config.demoMode ? ' · DEMO' : ''}',
                style:
                    const TextStyle(color: GvColors.textMuted, fontSize: 11)),
          ),
        ],
      ),
    );
  }

  Future<void> _selectLanguage(BuildContext context, WidgetRef ref) async {
    const languages = {
      'pt': 'Português',
      'en': 'English',
      'es': 'Español',
      'fr': 'Français',
    };
    final selected = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(AppLocalizations.of(sheetContext).language,
                style:
                    const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            for (final language in languages.entries)
              ListTile(
                title: Text(language.value),
                trailing: ref.read(localeProvider).languageCode == language.key
                    ? const Icon(Icons.check_circle,
                        color: GvColors.accentGreen)
                    : null,
                onTap: () => Navigator.pop(sheetContext, language.key),
              ),
          ],
        ),
      ),
    );
    if (selected != null) {
      await ref.read(localeProvider.notifier).select(Locale(selected));
    }
  }
}

class _Group extends StatelessWidget {
  const _Group({required this.children});
  final List<Widget> children;
  @override
  Widget build(BuildContext context) => GvCard(
        padding: EdgeInsets.zero,
        child: Column(children: children),
      );
}

class _Tile extends StatelessWidget {
  const _Tile({required this.icon, required this.label, required this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon, color: GvColors.accentCyan, size: 20),
        title: Text(label, style: const TextStyle(fontSize: 14)),
        trailing: const Icon(Icons.chevron_right,
            color: GvColors.textMuted, size: 18),
        onTap: onTap,
      );
}
