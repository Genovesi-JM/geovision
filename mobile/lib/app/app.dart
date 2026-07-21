import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme/app_theme.dart';
import '../core/widgets/env_banner.dart';
import '../l10n/app_localizations.dart';
import '../core/routing/app_router.dart';
import 'providers.dart';

class GeoVisionApp extends ConsumerWidget {
  const GeoVisionApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final config = ref.watch(appConfigProvider);

    return MaterialApp.router(
      title: 'GeoVision',
      debugShowCheckedModeBanner: false,
      theme: GvTheme.dark(),
      routerConfig: router,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      builder: (context, child) => EnvBanner(
        flavor: config.flavor,
        demoMode: config.demoMode,
        child: child ?? const SizedBox.shrink(),
      ),
    );
  }
}
