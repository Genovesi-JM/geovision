import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/account/presentation/account_screen.dart';
import '../../features/account/presentation/account_live_screen.dart';
import '../../features/account/presentation/payment_methods_screen.dart';
import '../../features/account/presentation/support_screen.dart';
import '../../features/assistant/presentation/gaia_screen.dart';
import '../../features/alerts/presentation/alert_detail_screen.dart';
import '../../features/alerts/presentation/alerts_screen.dart';
import '../../features/authentication/domain/auth_session.dart';
import '../../features/authentication/presentation/auth_controller.dart';
import '../../features/authentication/presentation/login_screen.dart';
import '../../features/authentication/presentation/reset_password_screen.dart';
import '../../features/authentication/presentation/register_screen.dart';
import '../../features/devices/presentation/devices_screen.dart';
import '../../features/drones/presentation/drones_screen.dart';
import '../../features/home/presentation/home_screen.dart';
import '../../features/guides/presentation/guides_screen.dart';
import '../../features/maps/presentation/site_map_screen.dart';
import '../../features/orders/presentation/orders_screen.dart';
import '../../features/orders/presentation/cart_screen.dart';
import '../../features/orders/presentation/order_detail_screen.dart';
import '../../features/orders/presentation/product_detail_screen.dart';
import '../../features/reports/presentation/reports_screen.dart';
import '../../features/sites/presentation/site_detail_screen.dart';
import '../../features/sites/presentation/new_site_screen.dart';
import '../../features/sites/presentation/sites_screen.dart';
import '../../features/work/presentation/new_request_screen.dart';
import '../../features/work/presentation/work_screen.dart';
import '../../app/app_shell.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authControllerProvider);

  return GoRouter(
    initialLocation: '/portal',
    redirect: (context, state) {
      final authRoute = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';
      if (auth.mode == AuthMode.unknown) return null;
      if (!auth.isSignedIn) return authRoute ? null : '/login';
      if (auth.isSignedIn && authRoute) return '/portal';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (c, s) => const LoginScreen()),
      GoRoute(path: '/register', builder: (c, s) => const RegisterScreen()),
      GoRoute(
        path: '/reset-password',
        builder: (c, s) => ResetPasswordScreen(
          token: s.uri.queryParameters['token'] ?? '',
        ),
      ),
      ShellRoute(
        builder: (c, s, child) => AppShell(child: child),
        routes: [
          GoRoute(path: '/portal', builder: (c, s) => const PortalScreen()),
          GoRoute(
            path: '/sites',
            builder: (c, s) => const SitesScreen(),
            routes: [
              GoRoute(path: 'new', builder: (c, s) => const NewSiteScreen()),
              GoRoute(
                  path: ':id',
                  builder: (c, s) =>
                      SiteDetailScreen(siteId: s.pathParameters['id']!)),
              GoRoute(
                  path: ':id/map',
                  builder: (c, s) =>
                      SiteMapScreen(siteId: s.pathParameters['id']!)),
            ],
          ),
          GoRoute(
            path: '/alerts',
            builder: (c, s) => const AlertsScreen(),
            routes: [
              GoRoute(
                  path: ':id',
                  builder: (c, s) =>
                      AlertDetailScreen(alertId: s.pathParameters['id']!)),
            ],
          ),
          GoRoute(
            path: '/work',
            builder: (c, s) => const WorkScreen(),
            routes: [
              GoRoute(path: 'new', builder: (c, s) => const NewRequestScreen()),
            ],
          ),
          GoRoute(path: '/account', builder: (c, s) => const AccountScreen()),
          GoRoute(
              path: '/account-live',
              builder: (c, s) => const AccountLiveScreen()),
          GoRoute(
            path: '/assistant',
            builder: (c, s) => GaiaScreen(
              siteId: s.uri.queryParameters['site'],
              productId: s.uri.queryParameters['product'],
              sourcePage: s.uri.queryParameters['from'] ?? 'assistant',
            ),
          ),
          GoRoute(path: '/support', builder: (c, s) => const SupportScreen()),
          GoRoute(
              path: '/payment-methods',
              builder: (c, s) => const PaymentMethodsScreen()),
          GoRoute(path: '/reports', builder: (c, s) => const ReportsScreen()),
          GoRoute(
            path: '/guides',
            builder: (c, s) => const GuidesScreen(),
            routes: [
              GoRoute(
                  path: ':id',
                  builder: (c, s) =>
                      GuideDetailScreen(guideId: s.pathParameters['id']!)),
            ],
          ),
          GoRoute(
            path: '/orders',
            builder: (c, s) => const OrdersScreen(),
            routes: [
              GoRoute(path: 'cart', builder: (c, s) => const CartScreen()),
              GoRoute(
                  path: 'product/:id',
                  builder: (c, s) =>
                      ProductDetailScreen(productId: s.pathParameters['id']!)),
              GoRoute(
                  path: ':id',
                  builder: (c, s) =>
                      OrderDetailScreen(orderId: s.pathParameters['id']!),
                  routes: [
                    GoRoute(
                        path: 'tracking',
                        builder: (c, s) => DeliveryTrackingScreen(
                            orderId: s.pathParameters['id']!)),
                  ]),
            ],
          ),
          GoRoute(path: '/devices', builder: (c, s) => const DevicesScreen()),
          GoRoute(path: '/drones', builder: (c, s) => const DronesScreen()),
        ],
      ),
    ],
  );
});
