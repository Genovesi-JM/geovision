import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme/app_theme.dart';
import '../core/widgets/env_banner.dart';
import '../l10n/app_localizations.dart';
import '../core/routing/app_router.dart';
import '../features/authentication/presentation/auth_controller.dart';
import '../features/notifications/data/notifications_repository.dart';
import 'providers.dart';

class GeoVisionApp extends ConsumerWidget {
  const GeoVisionApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final config = ref.watch(appConfigProvider);
    final locale = ref.watch(localeProvider);

    ref.listen(connectivityStatusProvider, (previous, next) {
      if (next.value == true && previous?.value != true) {
        ref.read(offlineSyncServiceProvider).syncNow();
      }
    });

    ref.listen(authControllerProvider, (previous, next) {
      if (next.isSignedIn && !next.isDemo && previous?.isSignedIn != true) {
        unawaited(_registerPushEndpoint(ref));
      }
    });

    ref.listen(pushNotificationTapProvider, (previous, next) {
      next.whenData((message) =>
          unawaited(_openPushNotification(ref, message.notificationId)));
    });

    return MaterialApp.router(
      title: 'GeoVision',
      debugShowCheckedModeBanner: false,
      theme: GvTheme.dark(),
      routerConfig: router,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      locale: locale,
      builder: (context, child) => EnvBanner(
        flavor: config.flavor,
        demoMode: config.demoMode,
        child: child ?? const SizedBox.shrink(),
      ),
    );
  }

  Future<void> _registerPushEndpoint(WidgetRef ref) async {
    final provider = ref.read(pushProviderProvider);
    final handle = await provider.register();
    if (handle == null || provider.backendProviderId.isEmpty) return;
    await ref.read(notificationsRepositoryProvider).registerCurrentEndpoint(
          provider: provider.backendProviderId,
          handle: handle,
        );
  }

  Future<void> _openPushNotification(
      WidgetRef ref, String notificationId) async {
    final repository = ref.read(notificationsRepositoryProvider);
    final resolved = await repository.resolveTarget(notificationId);
    await resolved.when(
      ok: (target) async {
        // Resolution already validates the target type, id, and exact route.
        await repository.markRead(notificationId);
        ref.read(routerProvider).go(target.appPath);
      },
      err: (_) async {},
    );
  }
}
