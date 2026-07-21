import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../domain/report.dart';

class ReportsRepository {
  ReportsRepository(this._config, this._api);
  final AppConfig _config;
  final ApiClient _api;

  Future<List<GvReport>> getReports() async {
    if (_config.demoMode) return DemoData.reports();
    final response = await _api.raw.get('/me/documents');
    return (response.data as List)
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
final reportsProvider = FutureProvider<List<GvReport>>(
    (ref) => ref.watch(reportsRepositoryProvider).getReports());
