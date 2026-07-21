import 'package:country_state_city/country_state_city.dart' as csc;

import 'angola_locations.dart';

class SiteCountry {
  const SiteCountry(this.code, this.name, this.flag);
  final String code;
  final String name;
  final String flag;
}

class SiteRegion {
  const SiteRegion(this.code, this.name);
  final String code;
  final String name;
}

/// Countries selected for GeoVision's initial African and Lusophone/European
/// commercial footprint. Data is bundled and works offline.
abstract final class SiteGeography {
  static const supportedCountryCodes = {
    'AO',
    'MZ',
    'NA',
    'ZM',
    'ZA',
    'CD',
    'CG',
    'PT',
    'ES',
    'FR',
    'BR',
  };

  static Future<List<SiteCountry>> countries() async {
    final all = await csc.getAllCountries();
    final selected = all
        .where((country) => supportedCountryCodes.contains(country.isoCode))
        .map((country) =>
            SiteCountry(country.isoCode, country.name, country.flag))
        .toList()
      ..sort((a, b) => a.name.compareTo(b.name));
    selected.sort((a, b) {
      if (a.code == 'AO') return -1;
      if (b.code == 'AO') return 1;
      return a.name.compareTo(b.name);
    });
    return selected;
  }

  static Future<List<SiteRegion>> regions(String countryCode) async {
    if (countryCode == 'AO') {
      return angolaMunicipalities.keys
          .map((name) => SiteRegion(name, name))
          .toList();
    }
    final states = await csc.getStatesOfCountry(countryCode);
    return states
        .map((state) => SiteRegion(state.isoCode, state.name))
        .toList();
  }

  static Future<List<String>> municipalities(
      String countryCode, SiteRegion region) async {
    if (countryCode == 'AO') {
      return angolaMunicipalities[region.name] ?? const [];
    }
    final cities = await csc.getStateCities(countryCode, region.code);
    return cities.map((city) => city.name).toSet().toList()..sort();
  }
}
