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
        workspaceId: _api.workspaceId ?? 'demo-workspace-spain-farm',
        organizationName: 'GeoVision España Demo',
        workspaceName: _api.workspaceId == 'demo-workspace-infrastructure'
            ? 'Infraestructuras Madrid'
            : 'Finca Madrid Norte',
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
            title: 'El fallo de riego requiere una decisión',
            summary: 'Revisar la bomba del Bloque A antes del próximo ciclo.',
            severity: 'critical',
          ),
          HomePriorityItem(
            id: 'home-action-scheduled',
            targetType: 'ACTION',
            targetId: 'action-demo-scheduled',
            title: 'Inspección de campo programada',
            summary: 'Equipo de campo GeoVision · mañana a las 09:00',
            severity: 'scheduled',
          ),
        ],
        latestResult: HomeResult(
          targetType: 'REPORT',
          targetId: 'rp-1',
          title: 'Informe de salud NDVI — Madrid Norte',
          summary: 'Resultado publicado del último vuelo multiespectral.',
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
