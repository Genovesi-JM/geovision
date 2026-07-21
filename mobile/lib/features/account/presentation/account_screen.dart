import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_flavor.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../authentication/presentation/auth_controller.dart';

class AccountScreen extends ConsumerWidget {
  const AccountScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(authControllerProvider);
    final config = ref.watch(appConfigProvider);
    final profile = session.profile;

    return Scaffold(
      appBar: AppBar(title: const Text('Account')),
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
          const SizedBox(height: GvSpacing.md),
          _Group(children: [
            _Tile(
                icon: Icons.notifications_outlined,
                label: 'Notification settings',
                onTap: () {}),
            _Tile(
                icon: Icons.description_outlined,
                label: 'Reports',
                onTap: () => context.go('/reports')),
            _Tile(
                icon: Icons.shopping_bag_outlined,
                label: 'Loja, pedidos & pagamentos',
                onTap: () => context.go('/orders')),
            _Tile(
                icon: Icons.sensors,
                label: 'Devices',
                onTap: () => context.go('/devices')),
            _Tile(
                icon: Icons.language,
                label: 'Language (EN / PT)',
                onTap: () {}),
          ]),
          const SizedBox(height: GvSpacing.md),
          _Group(children: [
            _Tile(icon: Icons.security, label: 'Security', onTap: () {}),
            _Tile(
                icon: Icons.privacy_tip_outlined,
                label: 'Privacy',
                onTap: () {}),
            _Tile(icon: Icons.gavel_outlined, label: 'Terms', onTap: () {}),
            _Tile(icon: Icons.support_agent, label: 'Support', onTap: () {}),
          ]),
          const SizedBox(height: GvSpacing.md),
          if (session.isDemo)
            FilledButton.icon(
              onPressed: () => context.go('/login'),
              icon: const Icon(Icons.login),
              label: const Text('Sign in to your account'),
            )
          else
            OutlinedButton.icon(
              onPressed: () async {
                await ref.read(authControllerProvider.notifier).logout();
                if (context.mounted) context.go('/login');
              },
              icon: const Icon(Icons.logout),
              label: const Text('Sign out'),
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
