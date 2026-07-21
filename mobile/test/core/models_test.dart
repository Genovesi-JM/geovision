import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/features/sites/domain/site.dart';
import 'package:geovision/features/sites/domain/angola_locations.dart';
import 'package:geovision/features/alerts/domain/alert.dart';
import 'package:geovision/features/sites/domain/kpi_definition.dart';
import 'package:geovision/features/sites/domain/sector.dart';

void main() {
  test('Angola location catalogue follows the 2025 administrative division',
      () {
    expect(angolaMunicipalities, hasLength(21));
    expect(
      angolaMunicipalities.values
          .fold<int>(0, (sum, rows) => sum + rows.length),
      326,
    );
    expect(angolaMunicipalities['Luanda'], contains('Viana'));
    expect(angolaMunicipalities['Icolo e Bengo'], contains('Catete'));
  });

  group('Site model', () {
    test('round-trips through JSON', () {
      final site = Site(
        id: 's1',
        name: 'Test',
        sector: Sector.agriculture,
        status: SiteStatus.active,
        location: 'Malanje',
        center: const GeoPoint(-9.5, 16.3),
        totalHectares: 100,
        kpis: [
          KpiValue(
              definitionId: 'ndvi_avg',
              label: 'NDVI',
              value: 0.7,
              updatedAt: DateTime(2026)),
        ],
      );
      final decoded = Site.fromJson(site.toJson());
      expect(decoded.id, 's1');
      expect(decoded.sector, Sector.agriculture);
      expect(decoded.kpis.first.value, 0.7);
    });
  });

  group('Alert model', () {
    test('acknowledge produces a new immutable copy', () {
      final a = GvAlert(
        id: 'a1',
        severity: 'critical',
        sector: 'agriculture',
        title: 't',
        description: 'd',
        createdAt: DateTime(2026),
      );
      final ack = a.copyWith(acknowledged: true);
      expect(a.acknowledged, false);
      expect(ack.acknowledged, true);
      expect(ack.id, 'a1');
    });
  });

  group('KPI catalogue', () {
    test('is sector-aware and agriculture-first', () {
      expect(KpiCatalogue.forSector(Sector.agriculture).length, greaterThan(5));
      expect(
          KpiCatalogue.forSector(Sector.agriculture)
              .any((k) => k.id == 'ndvi_avg'),
          true);
      expect(KpiCatalogue.forSector(Sector.livestock).isNotEmpty, true);
    });
  });
}
