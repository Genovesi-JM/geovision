import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/networking/api_client.dart';
import '../domain/location_search.dart';

class LocationSearchException implements Exception {
  const LocationSearchException(this.message);
  final String message;

  @override
  String toString() => message;
}

class LocationRepository {
  const LocationRepository(this._api, this._config);

  final ApiClient _api;
  final AppConfig _config;

  static const _demoLocations = <ResolvedLocation>[
    ResolvedLocation(
      providerReference: 'fake-luanda',
      displayName: 'Luanda',
      formattedAddress: 'Luanda, Angola',
      latitude: -8.838333,
      longitude: 13.234444,
    ),
    ResolvedLocation(
      providerReference: 'fake-madrid',
      displayName: 'Madrid',
      formattedAddress: 'Madrid, Espanha',
      latitude: 40.4168,
      longitude: -3.7038,
    ),
  ];

  Future<List<LocationSuggestion>> autocomplete({
    required String query,
    required String sessionToken,
    required String languageCode,
    String? regionCode,
    double? biasLatitude,
    double? biasLongitude,
  }) async {
    final normalized = query.trim();
    if (normalized.length < 2) return const [];
    if (_config.demoMode) {
      final needle = normalized.toLowerCase();
      return _demoLocations
          .where((item) =>
              item.displayName.toLowerCase().contains(needle) ||
              item.formattedAddress.toLowerCase().contains(needle))
          .map((item) => LocationSuggestion(
                providerReference: item.providerReference,
                primaryText: item.displayName,
                secondaryText: item.formattedAddress,
              ))
          .toList(growable: false);
    }

    final payload = <String, Object?>{
      'query': normalized,
      'session_token': sessionToken,
      'language_code': languageCode,
      if (regionCode != null && regionCode.isNotEmpty)
        'region_code': regionCode,
      if (biasLatitude != null && biasLongitude != null)
        'bias': {
          'latitude': biasLatitude,
          'longitude': biasLongitude,
        },
    };
    try {
      final response =
          await _api.raw.post('/location/places:autocomplete', data: payload);
      final body = Map<String, dynamic>.from(response.data as Map);
      return (body['suggestions'] as List<dynamic>? ?? const [])
          .map((item) => LocationSuggestion.fromJson(
              Map<String, dynamic>.from(item as Map)))
          .toList(growable: false);
    } catch (error) {
      throw LocationSearchException(_api.mapError(error).message);
    }
  }

  Future<ResolvedLocation> resolve({
    required String providerReference,
    required String sessionToken,
    required String languageCode,
  }) async {
    if (_config.demoMode) {
      for (final item in _demoLocations) {
        if (item.providerReference == providerReference) return item;
      }
      throw const LocationSearchException('Location is no longer available.');
    }

    try {
      final response = await _api.raw.post(
        '/location/places:resolve',
        data: {
          'provider_reference': providerReference,
          'session_token': sessionToken,
          'language_code': languageCode,
        },
      );
      return ResolvedLocation.fromJson(
          Map<String, dynamic>.from(response.data as Map));
    } catch (error) {
      throw LocationSearchException(_api.mapError(error).message);
    }
  }
}

final locationRepositoryProvider = Provider<LocationRepository>((ref) =>
    LocationRepository(
        ref.watch(apiClientProvider), ref.watch(appConfigProvider)));
