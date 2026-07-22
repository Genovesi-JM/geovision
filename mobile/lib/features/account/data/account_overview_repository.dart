import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/networking/api_client.dart';
import '../domain/account_overview.dart';

class AccountOverviewRepository {
  const AccountOverviewRepository(this._api, this._config);
  final ApiClient _api;
  final AppConfig _config;

  Future<AccountOverview> load() async {
    if (_config.demoMode) {
      return AccountOverview(
        organisationName: 'Fazenda Kilombo Agro',
        plan: 'Professional',
        status: 'active',
        currency: 'AOA',
        outstandingCents: 5424500,
        paidPayments: 8,
        pendingPayments: 1,
        sites: 3,
        orders: 12,
        activeOrders: 2,
        serviceRequests: 7,
        activeRequests: 2,
        lastUpdatedAt: DateTime.now(),
        recentOrders: const [
          AccountOrderSummary(
              id: 'demo-1',
              number: 'GV-2026-00187',
              status: 'dispatched',
              totalCents: 5424500,
              currency: 'AOA'),
          AccountOrderSummary(
              id: 'demo-2',
              number: 'GV-2026-00172',
              status: 'completed',
              totalCents: 12350000,
              currency: 'AOA'),
        ],
      );
    }
    final response = await _api.raw.get('/mobile/account/overview');
    return AccountOverview.fromJson(
        Map<String, dynamic>.from(response.data as Map));
  }
}

final accountOverviewRepositoryProvider = Provider<AccountOverviewRepository>(
    (ref) => AccountOverviewRepository(
        ref.watch(apiClientProvider), ref.watch(appConfigProvider)));

final accountOverviewProvider = FutureProvider.autoDispose<AccountOverview>(
    (ref) => ref.watch(accountOverviewRepositoryProvider).load());
