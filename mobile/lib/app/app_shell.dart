import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/widgets/sync_banner.dart';
import '../l10n/app_localizations.dart';
import 'providers.dart';

/// Customer shell focused on the five actions that fit reliably on a phone.
/// Secondary destinations remain one tap away from the More area.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.child});
  final Widget child;

  static const _tabs = [
    '/home',
    '/sites',
    '/devices',
    '/alerts',
    '/account',
  ];

  int _indexFor(String location) {
    if (location.startsWith('/account') ||
        location.startsWith('/orders') ||
        location.startsWith('/work') ||
        location.startsWith('/reports') ||
        location.startsWith('/guides')) {
      return 4;
    }
    for (var i = 0; i < _tabs.length; i++) {
      if (location.startsWith(_tabs[i])) return i;
    }
    return 0;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).matchedLocation;
    final index = _indexFor(location);
    final online = ref.watch(connectivityStatusProvider).value ?? true;
    final text = AppLocalizations.of(context);

    return Scaffold(
      body: Column(
        children: [
          SafeArea(bottom: false, child: SyncBanner(online: online)),
          Expanded(child: child),
        ],
      ),
      floatingActionButton: location == '/assistant'
          ? null
          : FloatingActionButton.small(
              heroTag: 'gaia-assistant',
              tooltip: 'GAIA',
              onPressed: () => context.go('/assistant'),
              child: const Icon(Icons.auto_awesome),
            ),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: index,
        selectedFontSize: 9,
        unselectedFontSize: 9,
        selectedItemColor: const Color(0xFF06B6D4),
        unselectedItemColor: const Color(0xFF64748B),
        backgroundColor: const Color(0xFF020617),
        onTap: (i) => context.go(_tabs[i]),
        items: [
          BottomNavigationBarItem(
              icon: const Icon(Icons.home_outlined),
              activeIcon: const Icon(Icons.home),
              label: text.navHome),
          BottomNavigationBarItem(
              icon: const Icon(Icons.terrain_outlined),
              activeIcon: const Icon(Icons.terrain),
              label: text.navAssets),
          BottomNavigationBarItem(
              icon: const Icon(Icons.sensors_outlined),
              activeIcon: const Icon(Icons.sensors),
              label: text.devices),
          BottomNavigationBarItem(
              icon: const Icon(Icons.notifications_outlined),
              activeIcon: const Icon(Icons.notifications),
              label: text.navAlerts),
          BottomNavigationBarItem(
              icon: const Icon(Icons.grid_view_outlined),
              activeIcon: const Icon(Icons.grid_view),
              label: text.navMore),
        ],
      ),
    );
  }
}
