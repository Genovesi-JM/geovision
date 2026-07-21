import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/widgets/sync_banner.dart';
import '../l10n/app_localizations.dart';
import 'providers.dart';

/// Customer shell with direct access to the most frequent field and commercial
/// actions. Compact labels keep all destinations usable on phone screens.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.child});
  final Widget child;

  static const _tabs = [
    '/home',
    '/sites',
    '/alerts',
    '/work',
    '/work/new',
    '/orders',
    '/account',
  ];

  int _indexFor(String location) {
    if (location.startsWith('/work/new')) return 4;
    if (location.startsWith('/orders')) return 5;
    if (location.startsWith('/account')) return 6;
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
              label: text.navSites),
          BottomNavigationBarItem(
              icon: const Icon(Icons.notifications_outlined),
              activeIcon: const Icon(Icons.notifications),
              label: text.navAlerts),
          BottomNavigationBarItem(
              icon: const Icon(Icons.work_outline),
              activeIcon: const Icon(Icons.work),
              label: text.navWork),
          BottomNavigationBarItem(
              icon: const Icon(Icons.add_circle_outline),
              activeIcon: const Icon(Icons.add_circle),
              label: text.navRequest),
          BottomNavigationBarItem(
              icon: const Icon(Icons.storefront_outlined),
              activeIcon: const Icon(Icons.storefront),
              label: text.navStore),
          BottomNavigationBarItem(
              icon: const Icon(Icons.person_outline),
              activeIcon: const Icon(Icons.person),
              label: text.navAccount),
        ],
      ),
    );
  }
}
