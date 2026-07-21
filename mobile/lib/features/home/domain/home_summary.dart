import '../../alerts/domain/alert.dart';
import '../../reports/domain/report.dart';
import '../../sites/domain/site.dart';
import '../../work/domain/service_request.dart';

class HomeSummary {
  const HomeSummary({
    required this.organisation,
    required this.selectedSite,
    required this.criticalAlerts,
    required this.activeRequests,
    required this.latestReport,
    required this.onlineDevices,
    required this.totalDevices,
    required this.lastSyncedAt,
    required this.fromCache,
  });

  final String organisation;
  final Site? selectedSite;
  final List<GvAlert> criticalAlerts;
  final List<ServiceRequest> activeRequests;
  final GvReport? latestReport;
  final int onlineDevices;
  final int totalDevices;
  final DateTime? lastSyncedAt;
  final bool fromCache;
}
