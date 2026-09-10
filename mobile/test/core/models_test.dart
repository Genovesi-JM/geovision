import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/features/sites/domain/site.dart';
import 'package:geovision/features/sites/domain/angola_locations.dart';
import 'package:geovision/features/alerts/domain/alert.dart';
import 'package:geovision/features/sites/domain/kpi_definition.dart';
import 'package:geovision/features/sites/domain/sector.dart';
import 'package:geovision/features/sites/domain/site_geography.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

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

  test('site geography includes international GeoVision markets', () async {
    final countries = await SiteGeography.countries();
    expect(countries.map((item) => item.code),
        containsAll(['AO', 'MZ', 'NA', 'ZA', 'PT', 'ES', 'FR', 'BR']));
    final portugal = await SiteGeography.regions('PT');
    expect(portugal, isNotEmpty);
    final cities = await SiteGeography.municipalities('PT', portugal.first);
    expect(cities, isNotEmpty);
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

    test('rejects absent and unknown sectors instead of inventing a fallback',
        () {
      final json = <String, dynamic>{
        'id': 's2',
        'name': 'Strict site',
        'status': 'active',
        'location': 'Luanda',
        'center': {'lat': -8.8, 'lng': 13.2},
      };

      expect(() => Site.fromJson(json), throwsFormatException);
      expect(
        () => Site.fromJson({...json, 'sector': ''}),
        throwsFormatException,
      );
      expect(
        () => Site.fromJson({...json, 'sector': 'future_sector'}),
        throwsFormatException,
      );
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

    test('normalizes legacy API sector values', () {
      final alert = GvAlert.fromJson({
        'id': 'a2',
        'severity': 'medium',
        'sector': 'PORTS_INDUSTRIAL',
        'title': 't',
        'description': 'd',
      });
      expect(alert.sector, PublicSectorIds.portsLogistics);
    });
  });

  group('KPI catalogue', () {
    test('is sector-aware and agriculture-first', () {
      expect(KpiCatalogue.forSector(Sector.agriculture).length, greaterThan(5));
      expect(
          KpiCatalogue.forSector(Sector.agriculture)
              .any((k) => k.id == 'ndvi_avg'),
          true);
      expect(sectorFromString('livestock'), Sector.agriculture);
      expect(sectorFromString('mining'), Sector.mining);
    });

    test('canonical IDs and legacy aliases resolve to the six public sectors',
        () {
      expect(Sector.values.map((sector) => sector.id).toList(),
          PublicSectorIds.values);
      expect(canonicalSectorId('agro'), PublicSectorIds.agriculture);
      expect(canonicalSectorId('infrastructure'),
          PublicSectorIds.constructionInfrastructure);
      expect(canonicalSectorId('environmental'), PublicSectorIds.environment);
      expect(canonicalSectorId('industry'),
          PublicSectorIds.industryEnergyUtilities);
      expect(canonicalSectorId('PORTS_INDUSTRIAL'),
          PublicSectorIds.portsLogistics);
      expect(
        canonicalSectorId('Indústria, Energia & Utilities'),
        PublicSectorIds.industryEnergyUtilities,
      );
      expect(
        canonicalSectorId('Agricultura e Pecuária'),
        PublicSectorIds.agriculture,
      );
      expect(
        canonicalSectorId('Construção e Infraestruturas'),
        PublicSectorIds.constructionInfrastructure,
      );
      expect(
        canonicalSectorId('Portos e Logística'),
        PublicSectorIds.portsLogistics,
      );
      expect(canonicalSectorId('ports'), PublicSectorIds.portsLogistics);
      expect(canonicalSectorId('industry_energy'),
          PublicSectorIds.industryEnergyUtilities);
      expect(canonicalSectorId('Portos & Logística'),
          PublicSectorIds.portsLogistics);
      expect(canonicalSectorId('future_sector'), 'future_sector');
    });

    test('known CSV labels resolve without splitting the industry sector', () {
      expect(
        parseCanonicalSectorIds(
          'Agricultura & Pecuária,Construção & Infraestruturas,Ambiente,'
          'Mineração,Indústria, Energia & Utilities,Portos & Logística',
        ),
        PublicSectorIds.values,
      );
      expect(
        parseCanonicalSectorIds([
          'Indústria, Energia & Utilities',
          'future_sector',
          'ports',
        ]),
        const [
          PublicSectorIds.industryEnergyUtilities,
          PublicSectorIds.portsLogistics,
        ],
      );
    });

    test('Portuguese labels match the public sector taxonomy', () {
      expect(Sector.values.map((sector) => sector.label).toList(), const [
        'Agricultura & Pecuária',
        'Construção & Infraestruturas',
        'Ambiente',
        'Mineração',
        'Indústria, Energia & Utilities',
        'Portos & Logística',
      ]);
    });

    test('unknown sectors fail explicitly', () {
      expect(() => sectorFromString('home'), throwsFormatException);
    });
  });
}
