import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/app_shell.dart';
import '../../features/account/presentation/account_live_screen.dart';
import '../../features/account/presentation/account_screen.dart';
import '../../features/account/presentation/customer_context_widgets.dart';
import '../../features/account/presentation/customer_settings_screen.dart';
import '../../features/account/presentation/payment_methods_screen.dart';
import '../../features/account/presentation/support_screen.dart';
import '../../features/account/presentation/team_screen.dart';
import '../../features/actions/presentation/action_detail_screen.dart';
import '../../features/actions/presentation/actions_screen.dart';
import '../../features/alerts/presentation/alert_detail_screen.dart';
import '../../features/assets/presentation/asset_detail_screen.dart';
import '../../features/assets/presentation/asset_map_screen.dart';
import '../../features/assets/presentation/assets_screen.dart';
import '../../features/assistant/presentation/gaia_screen.dart';
import '../../features/authentication/domain/auth_session.dart';
import '../../features/authentication/presentation/auth_controller.dart';
import '../../features/authentication/presentation/login_screen.dart';
import '../../features/authentication/presentation/register_screen.dart';
import '../../features/authentication/presentation/reset_password_screen.dart';
import '../../features/devices/presentation/devices_screen.dart';
import '../../features/drones/presentation/drones_screen.dart';
import '../../features/guides/presentation/guides_screen.dart';
import '../../features/home/presentation/home_screen.dart';
import '../../features/invitations/presentation/invitation_accept_screen.dart';
import '../../features/notifications/presentation/notification_context_screen.dart';
import '../../features/notifications/presentation/notification_preferences_screen.dart';
import '../../features/notifications/presentation/notifications_screen.dart';
import '../../features/orders/presentation/cart_screen.dart';
import '../../features/orders/presentation/order_detail_screen.dart';
import '../../features/orders/presentation/orders_screen.dart';
import '../../features/orders/presentation/product_detail_screen.dart';
import '../../features/reports/presentation/reports_screen.dart';
import '../../features/sites/presentation/new_site_screen.dart';
import '../../features/work/presentation/new_request_screen.dart';
import '../../features/work/presentation/service_request_detail_screen.dart';
import '../../features/work/presentation/work_screen.dart';

final _homeNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'home');
final _assetsNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'assets');
final _actionsNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'actions');
final _servicesNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'services');
final _moreNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'more');

Widget _capability(String capability, String title, Widget child) =>
    CustomerCapabilityPage(
      capability: capability,
      title: title,
      child: child,
    );

final routerProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authControllerProvider);

  String? safeReturn(String? value) {
    if (value == null || !value.startsWith('/') || value.startsWith('//')) {
      return null;
    }
    final uri = Uri.tryParse(value);
    if (uri == null || uri.hasScheme || uri.host.isNotEmpty) return null;
    return value;
  }

  return GoRouter(
    initialLocation: '/home',
    redirect: (context, state) {
      final authRoute = state.matchedLocation == '/login' ||
          state.matchedLocation == '/register';
      if (auth.mode == AuthMode.unknown) return null;
      if (!auth.isSignedIn) {
        if (authRoute) return null;
        return Uri(
          path: '/login',
          queryParameters: {'return': state.uri.toString()},
        ).toString();
      }
      if (auth.isSignedIn && authRoute) {
        return safeReturn(state.uri.queryParameters['return']) ?? '/home';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => LoginScreen(
          returnTo: safeReturn(state.uri.queryParameters['return']),
        ),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => RegisterScreen(
          returnTo: safeReturn(state.uri.queryParameters['return']),
        ),
      ),
      GoRoute(
        path: '/reset-password',
        builder: (context, state) => ResetPasswordScreen(
          token: state.uri.queryParameters['token'] ?? '',
        ),
      ),
      GoRoute(
        path: '/invitation/accept',
        builder: (context, state) {
          final fragment = Uri.splitQueryString(
            state.uri.fragment.startsWith('token=') ? state.uri.fragment : '',
          );
          return InvitationAcceptScreen(
            initialToken:
                state.uri.queryParameters['token'] ?? fragment['token'],
          );
        },
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            AppShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            navigatorKey: _homeNavigatorKey,
            routes: [
              GoRoute(
                path: '/home',
                builder: (context, state) => const HomeScreen(),
              ),
              GoRoute(path: '/portal', redirect: (context, state) => '/home'),
            ],
          ),
          StatefulShellBranch(
            navigatorKey: _assetsNavigatorKey,
            routes: [
              GoRoute(
                path: '/assets',
                builder: (context, state) =>
                    _capability('assets', 'Assets', const AssetsScreen()),
                routes: [
                  GoRoute(
                    path: 'new',
                    builder: (context, state) => _capability(
                      'assets',
                      'Add asset',
                      const NewSiteScreen(),
                    ),
                  ),
                  GoRoute(
                    path: ':id/map',
                    builder: (context, state) => _capability(
                      'assets',
                      'Asset map',
                      AssetMapScreen(assetId: state.pathParameters['id']!),
                    ),
                  ),
                  GoRoute(
                    path: ':id',
                    builder: (context, state) => _capability(
                      'assets',
                      'Asset detail',
                      AssetDetailScreen(assetId: state.pathParameters['id']!),
                    ),
                  ),
                ],
              ),
              GoRoute(
                path: '/sites',
                redirect: (context, state) =>
                    state.uri.path == '/sites' ? '/assets' : null,
                routes: [
                  GoRoute(
                    path: 'new',
                    redirect: (context, state) => '/assets/new',
                  ),
                  GoRoute(
                    path: ':id/map',
                    redirect: (context, state) =>
                        '/assets/${state.pathParameters['id']}/map',
                  ),
                  GoRoute(
                    path: ':id',
                    redirect: (context, state) =>
                        '/assets/${state.pathParameters['id']}',
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            navigatorKey: _actionsNavigatorKey,
            routes: [
              GoRoute(
                path: '/actions',
                builder: (context, state) => _capability(
                  'actions',
                  'Actions',
                  ActionsScreen(
                    assetId: state.uri.queryParameters['asset_id'],
                  ),
                ),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (context, state) => _capability(
                      'actions',
                      'Action detail',
                      ActionDetailScreen(
                        actionId: state.pathParameters['id']!,
                      ),
                    ),
                  ),
                ],
              ),
              GoRoute(
                path: '/alerts',
                redirect: (context, state) =>
                    state.uri.path == '/alerts' ? '/actions' : null,
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (context, state) =>
                        AlertDetailScreen(alertId: state.pathParameters['id']!),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            navigatorKey: _servicesNavigatorKey,
            routes: [
              GoRoute(
                path: '/services',
                builder: (context, state) => _capability(
                  'services',
                  'Services',
                  const OrdersScreen(),
                ),
                routes: [
                  GoRoute(
                    path: 'cart',
                    builder: (context, state) =>
                        _capability('services', 'Cart', const CartScreen()),
                  ),
                  GoRoute(
                    path: 'product/:id',
                    builder: (context, state) => _capability(
                      'services',
                      'Service detail',
                      ProductDetailScreen(
                        productId: state.pathParameters['id']!,
                      ),
                    ),
                  ),
                  GoRoute(
                    path: 'orders/:id',
                    builder: (context, state) => _capability(
                      'services',
                      'Order detail',
                      OrderDetailScreen(orderId: state.pathParameters['id']!),
                    ),
                    routes: [
                      GoRoute(
                        path: 'tracking',
                        builder: (context, state) => DeliveryTrackingScreen(
                          orderId: state.pathParameters['id']!,
                        ),
                      ),
                    ],
                  ),
                  GoRoute(
                    path: ':id',
                    builder: (context, state) => _capability(
                      'services',
                      'Service detail',
                      NotificationContextScreen(
                        targetType: 'SERVICE',
                        targetId: state.pathParameters['id']!,
                      ),
                    ),
                  ),
                ],
              ),
              GoRoute(
                path: '/orders',
                redirect: (context, state) =>
                    state.uri.path == '/orders' ? '/services' : null,
                routes: [
                  GoRoute(
                    path: 'cart',
                    redirect: (context, state) => '/services/cart',
                  ),
                  GoRoute(
                    path: 'product/:id',
                    redirect: (context, state) =>
                        '/services/product/${state.pathParameters['id']}',
                  ),
                  GoRoute(
                    path: ':id/tracking',
                    redirect: (context, state) =>
                        '/services/orders/${state.pathParameters['id']}/tracking',
                  ),
                  GoRoute(
                    path: ':id',
                    redirect: (context, state) =>
                        '/services/orders/${state.pathParameters['id']}',
                  ),
                ],
              ),
              GoRoute(
                path: '/work',
                builder: (context, state) => _capability(
                  'services',
                  'Service requests',
                  const WorkScreen(),
                ),
                routes: [
                  GoRoute(
                    path: 'new',
                    builder: (context, state) => _capability(
                      'services',
                      'Request service',
                      const NewRequestScreen(),
                    ),
                  ),
                  GoRoute(
                    path: ':id',
                    builder: (context, state) => _capability(
                      'services',
                      'Service result',
                      ServiceRequestDetailScreen(
                        requestId: state.pathParameters['id']!,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            navigatorKey: _moreNavigatorKey,
            routes: [
              GoRoute(
                path: '/more',
                builder: (context, state) => const AccountScreen(),
              ),
              GoRoute(path: '/account', redirect: (context, state) => '/more'),
              GoRoute(
                path: '/notifications',
                builder: (context, state) => const NotificationsScreen(),
              ),
              GoRoute(
                path: '/notification-preferences',
                builder: (context, state) =>
                    const NotificationPreferencesScreen(),
              ),
              GoRoute(
                path: '/account-live',
                builder: (context, state) => _capability(
                  'billing',
                  'Billing',
                  const AccountLiveScreen(),
                ),
              ),
              GoRoute(
                path: '/team',
                builder: (context, state) =>
                    _capability('team', 'Team', const TeamScreen()),
              ),
              GoRoute(
                path: '/settings',
                builder: (context, state) => _capability(
                  'settings',
                  'Settings',
                  const CustomerSettingsScreen(),
                ),
              ),
              GoRoute(
                path: '/assistant',
                builder: (context, state) => GaiaScreen(
                  siteId: state.uri.queryParameters['site'],
                  productId: state.uri.queryParameters['product'],
                  sourcePage: state.uri.queryParameters['from'] ?? 'assistant',
                ),
              ),
              GoRoute(
                path: '/support',
                builder: (context, state) => _capability(
                  'support',
                  'Support',
                  const SupportScreen(),
                ),
              ),
              GoRoute(
                path: '/payment-methods',
                builder: (context, state) => _capability(
                  'billing',
                  'Payment methods',
                  const PaymentMethodsScreen(),
                ),
              ),
              GoRoute(
                path: '/reports',
                builder: (context, state) => _capability(
                  'reports',
                  'Reports',
                  ReportsScreen(assetId: state.uri.queryParameters['asset_id']),
                ),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (context, state) => _capability(
                      'reports',
                      'Report',
                      NotificationContextScreen(
                        targetType: 'REPORT',
                        targetId: state.pathParameters['id']!,
                      ),
                    ),
                  ),
                ],
              ),
              GoRoute(
                path: '/guides',
                builder: (context, state) => const GuidesScreen(),
                routes: [
                  GoRoute(
                    path: ':id',
                    builder: (context, state) =>
                        GuideDetailScreen(guideId: state.pathParameters['id']!),
                  ),
                ],
              ),
              GoRoute(
                path: '/devices',
                builder: (context, state) => _capability(
                  'devices',
                  'Devices',
                  const DevicesScreen(),
                ),
              ),
              GoRoute(
                path: '/drones',
                builder: (context, state) => const DronesScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
