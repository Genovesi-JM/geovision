import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../../account/data/customer_experience_repository.dart';
import '../domain/report.dart';

class ReportsRepository {
  ReportsRepository(this._config, this._api);
  final AppConfig _config;
  final ApiClient _api;

  Future<List<GvReport>> getReports({String? assetId}) async {
    if (_config.demoMode) return DemoData.reports();
    final response = await _api.raw.get(
      '/reports',
      queryParameters: {
        'status': 'PUBLISHED',
        if (assetId != null) 'asset_id': assetId,
      },
    );
    final body = response.data;
    final rows = body is Map ? body['items'] as List? ?? const [] : const [];
    return rows
        .map((item) => GvReport.fromJson((item as Map).cast<String, dynamic>()))
        .toList();
  }
}

final reportsRepositoryProvider = Provider<ReportsRepository>(
  (ref) => ReportsRepository(
    ref.watch(appConfigProvider),
    ref.watch(apiClientProvider),
  ),
);
final reportsProvider = FutureProvider<List<GvReport>>((ref) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(reportsRepositoryProvider).getReports();
});

final assetReportsProvider =
    FutureProvider.family<List<GvReport>, String>((ref, assetId) async {
  await ref.watch(customerExperienceProvider.future);
  return ref.watch(reportsRepositoryProvider).getReports(assetId: assetId);
});
