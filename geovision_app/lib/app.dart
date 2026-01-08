import 'package:flutter/material.dart';

import 'auth/login_screen.dart';
import 'screens/admin/admin_screen.dart';
import 'screens/dashboard/dashboard_screen.dart';
import 'screens/landing/landing_screen.dart';
import 'screens/sector/sector_screen.dart';
import 'screens/store/store_screen.dart';
import 'services/api_client.dart';
import 'theme/app_theme.dart';

class GeoVisionApp extends StatelessWidget {
  const GeoVisionApp({super.key, required this.initialSignedIn});

  final bool initialSignedIn;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'GeoVision',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      home: initialSignedIn ? const GeoVisionShell() : const LoginScreen(),
      routes: {
        '/app': (_) => const GeoVisionShell(),
      },
    );
  }
}

class GeoVisionShell extends StatefulWidget {
  const GeoVisionShell({super.key});

  @override
  State<GeoVisionShell> createState() => _GeoVisionShellState();
}

class _GeoVisionShellState extends State<GeoVisionShell> {
  int _index = 0;

  static const _pages = <Widget>[
    LandingScreen(),
    DashboardScreen(),
    SectorScreen(),
    StoreScreen(),
    AdminScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_titleForIndex(_index)),
        actions: [
          IconButton(
            tooltip: 'Terminar sessão',
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await ApiClient.instance.clearToken();
              if (!mounted) return;
              Navigator.of(context).pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (route) => false,
              );
            },
          ),
        ],
      ),
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 250),
        child: _pages[_index],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) {
          setState(() {
            _index = value;
          });
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Home',
          ),
          NavigationDestination(
            icon: Icon(Icons.bar_chart_outlined),
            selectedIcon: Icon(Icons.bar_chart),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map),
            label: 'Sectors',
          ),
          NavigationDestination(
            icon: Icon(Icons.storefront_outlined),
            selectedIcon: Icon(Icons.storefront),
            label: 'Store',
          ),
          NavigationDestination(
            icon: Icon(Icons.admin_panel_settings_outlined),
            selectedIcon: Icon(Icons.admin_panel_settings),
            label: 'Admin',
          ),
        ],
      ),
    );
  }

  String _titleForIndex(int index) {
    switch (index) {
      case 0:
        return 'GeoVision';
      case 1:
        return 'Dashboard';
      case 2:
        return 'Sectors';
      case 3:
        return 'Store';
      case 4:
        return 'Admin';
      default:
        return 'GeoVision';
    }
  }
}
