import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/widgets/sync_banner.dart';
import '../features/account/presentation/customer_context_widgets.dart';
import '../l10n/app_localizations.dart';
import 'providers.dart';

/// Exactly five durable customer destinations. Each tab owns a navigator so
/// switching tabs preserves its contextual back stack.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final online = ref.watch(connectivityStatusProvider).value ?? true;
    final text = AppLocalizations.of(context);
    final location = GoRouterState.of(context).uri.path;

    return Scaffold(
      body: Column(
        children: [
          SafeArea(bottom: false, child: SyncBanner(online: online)),
          const CustomerWorkspaceBar(),
          Expanded(child: navigationShell),
        ],
      ),
      floatingActionButton: location == '/assistant'
          ? null
          : FloatingActionButton.small(
              heroTag: 'gaia-assistant',
              tooltip: 'GAIA',
              onPressed: () => context.push('/assistant'),
              child: const Icon(Icons.auto_awesome),
            ),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        currentIndex: navigationShell.currentIndex,
        selectedFontSize: 10,
        unselectedFontSize: 10,
        selectedItemColor: const Color(0xFF22C55E),
        unselectedItemColor: const Color(0xFF64748B),
        backgroundColor: const Color(0xFF020617),
        onTap: (index) => navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        ),
        items: [
          BottomNavigationBarItem(
            icon: const Icon(Icons.home_outlined),
            activeIcon: const Icon(Icons.home),
            label: text.navHome,
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.terrain_outlined),
            activeIcon: const Icon(Icons.terrain),
            label: text.navAssets,
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.task_alt_outlined),
            activeIcon: const Icon(Icons.task_alt),
            label: text.navActions,
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.design_services_outlined),
            activeIcon: const Icon(Icons.design_services),
            label: text.navServices,
          ),
          BottomNavigationBarItem(
            icon: const Icon(Icons.grid_view_outlined),
            activeIcon: const Icon(Icons.grid_view),
            label: text.navMore,
          ),
        ],
      ),
    );
  }
}
