import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/demo/demo_data.dart';
import '../../alerts/data/alerts_repository.dart';
import '../../devices/data/devices_repository.dart';
import '../../reports/data/reports_repository.dart';
import '../../sites/data/sites_repository.dart';
import '../../sites/domain/site.dart';
import '../../work/data/work_repository.dart';
import '../domain/home_summary.dart';

class HomeRepository {
  HomeRepository(this._ref);
  final Ref _ref;

  Future<HomeSummary> load(String? selectedSiteId) async {
    final sitesEnv = await _ref.read(sitesRepositoryProvider).getSites();
    final alertsEnv = await _ref.read(alertsRepositoryProvider).getAlerts();
    final requests = await _ref.read(workRepositoryProvider).getRequests();
    final reports = await _ref.read(reportsRepositoryProvider).getReports();
    final devices = await _ref.read(devicesRepositoryProvider).getDevices();

    final sites = sitesEnv.value;
    Site? site;
    if (sites.isNotEmpty) {
      site = sites.first;
      if (selectedSiteId != null) {
        for (final s in sites) {
          if (s.id == selectedSiteId) {
            site = s;
            break;
          }
        }
      }
    }

    return HomeSummary(
      organisation: DemoData.organisation,
      selectedSite: site,
      criticalAlerts: alertsEnv.value
          .where((a) =>
              (a.severity == 'critical' || a.severity == 'high') && !a.resolved)
          .toList(),
      activeRequests: requests.where((r) => r.status != 'completed').toList(),
      latestReport: reports.isNotEmpty ? reports.first : null,
      onlineDevices: devices.where((d) => d.status == 'online').length,
      totalDevices: devices.length,
      lastSyncedAt: sitesEnv.syncedAt,
      fromCache: sitesEnv.fromCache,
    );
  }
}

final homeRepositoryProvider =
    Provider<HomeRepository>((ref) => HomeRepository(ref));

final homeSummaryProvider = FutureProvider<HomeSummary>((ref) {
  final id = ref.watch(selectedSiteIdProvider);
  return ref.watch(homeRepositoryProvider).load(id);
});
