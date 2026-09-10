import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/networking/api_client.dart';
import '../../account/data/customer_experience_repository.dart';
import '../domain/home_summary.dart';

class HomeRepository {
  const HomeRepository(this._api, this._config);
  final ApiClient _api;
  final AppConfig _config;

  Future<HomeSummary> load() async {
    if (_config.demoMode) return _demo();
    final response = await _api.raw.get('/mobile/home');
    return HomeSummary.fromJson(
        Map<String, dynamic>.from(response.data as Map));
  }

  HomeSummary _demo() => HomeSummary(
        workspaceId: _api.workspaceId ?? 'demo-workspace-farm',
        organizationName: 'Fazenda Kilombo Agro',
        workspaceName: _api.workspaceId == 'demo-workspace-infrastructure'
            ? 'Luanda Infrastructure'
            : 'Kilombo Farm',
        attention: const HomeAttention(
          critical: 1,
          attention: 2,
          scheduled: 1,
          completedRecent: 1,
          activeServices: 1,
          offlineDevices: 1,
        ),
        priorityItems: const [
          HomePriorityItem(
            id: 'home-action-critical',
            targetType: 'ACTION',
            targetId: 'action-demo-critical',
            title: 'Irrigation failure needs a decision',
            summary: 'Inspect the Block A pump before the next cycle.',
            severity: 'critical',
          ),
          HomePriorityItem(
            id: 'home-action-scheduled',
            targetType: 'ACTION',
            targetId: 'action-demo-scheduled',
            title: 'Field inspection scheduled',
            summary: 'GeoVision Field Team · tomorrow at 09:00',
            severity: 'scheduled',
          ),
        ],
        latestResult: HomeResult(
          targetType: 'REPORT',
          targetId: 'rp-1',
          title: 'NDVI Health Report — Kilombo North',
          summary: 'Published result from the latest multispectral survey.',
          completedAt: DateTime(2026, 9, 9),
        ),
        updatedAt: DateTime.now().toUtc(),
      );
}

final homeRepositoryProvider = Provider<HomeRepository>((ref) =>
    HomeRepository(ref.watch(apiClientProvider), ref.watch(appConfigProvider)));

final homeSummaryProvider = FutureProvider<HomeSummary>((ref) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(homeRepositoryProvider).load();
});
