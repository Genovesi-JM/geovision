import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../domain/report.dart';

class ReportsRepository {
  ReportsRepository(this._config);
  final AppConfig _config;

  Future<List<GvReport>> getReports() async {
    if (_config.demoMode) return DemoData.reports();
    // Real mode: GET /me/documents (mapped) — placeholder returns empty until wired.
    return DemoData.reports();
  }
}

final reportsRepositoryProvider = Provider<ReportsRepository>(
    (ref) => ReportsRepository(ref.watch(appConfigProvider)));
final reportsProvider = FutureProvider<List<GvReport>>(
    (ref) => ref.watch(reportsRepositoryProvider).getReports());
