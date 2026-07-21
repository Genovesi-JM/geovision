import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/demo/demo_data.dart';

void main() {
  test('demo dataset covers the full navigation surface', () {
    expect(DemoData.sites().length, greaterThanOrEqualTo(2));
    expect(DemoData.alerts().any((a) => a.severity == 'critical'), true);
    expect(DemoData.serviceRequests().isNotEmpty, true);
    expect(DemoData.reports().isNotEmpty, true);
    expect(DemoData.devices().isNotEmpty, true);
    expect(DemoData.products().isNotEmpty, true);
    expect(DemoData.orders().isNotEmpty, true);
  });

  test('agricultural site has fields and KPIs', () {
    final agri = DemoData.sites().firstWhere((s) => s.areas.isNotEmpty);
    expect(agri.areas.length, greaterThanOrEqualTo(2));
    expect(agri.kpis.any((k) => k.definitionId == 'ndvi_avg'), true);
  });
}
