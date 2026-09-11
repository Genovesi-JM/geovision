import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../../../app/providers.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../data/location_repository.dart';
import '../domain/location_search.dart';
import '../domain/site.dart';

class LocationPickerScreen extends ConsumerStatefulWidget {
  const LocationPickerScreen({super.key, this.initial, this.regionCode});
  final GeoPoint? initial;
  final String? regionCode;

  @override
  ConsumerState<LocationPickerScreen> createState() =>
      _LocationPickerScreenState();
}

class _LocationPickerScreenState extends ConsumerState<LocationPickerScreen> {
  final mapController = MapController();
  final searchController = TextEditingController();
  late LatLng selected = widget.initial == null
      ? const LatLng(-11.2027, 17.8739)
      : LatLng(widget.initial!.lat, widget.initial!.lng);
  bool locating = false;
  bool searching = false;
  Timer? searchDebounce;
  List<LocationSuggestion> suggestions = const [];
  String? searchError;
  late String searchSessionToken = _newSessionToken();

  @override
  void dispose() {
    searchDebounce?.cancel();
    searchController.dispose();
    super.dispose();
  }

  String _t(String pt, String en, String es, String fr) =>
      switch (Localizations.localeOf(context).languageCode) {
        'pt' => pt,
        'es' => es,
        'fr' => fr,
        _ => en,
      };

  @override
  Widget build(BuildContext context) {
    final mapProvider = ref.watch(locationMapProviderProvider);
    final tileUrl = mapProvider.tileUrlTemplate();
    final language = Localizations.localeOf(context).languageCode;
    String t(String pt, String en, String es, String fr) => switch (language) {
          'pt' => pt,
          'es' => es,
          'fr' => fr,
          _ => en,
        };
    return Scaffold(
      appBar: AppBar(
        title: Text(t('Localização precisa', 'Precise location',
            'Ubicación precisa', 'Localisation précise')),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(
              context,
              GeoPoint(selected.latitude, selected.longitude),
            ),
            child: Text(t('Confirmar', 'Confirm', 'Confirmar', 'Confirmer')),
          ),
        ],
      ),
      body: Stack(children: [
        FlutterMap(
          mapController: mapController,
          options: MapOptions(
            initialCenter: selected,
            initialZoom: widget.initial == null ? 5.5 : 16,
            onTap: (_, point) => setState(() => selected = point),
          ),
          children: [
            TileLayer(
              urlTemplate: tileUrl!,
              userAgentPackageName: 'com.geovision.geovision',
              maxZoom: mapProvider.maxZoom,
            ),
            MarkerLayer(markers: [
              Marker(
                point: selected,
                width: 48,
                height: 48,
                child: const Icon(Icons.location_pin,
                    size: 48, color: GvColors.critical),
              ),
            ]),
          ],
        ),
        Positioned(
          left: GvSpacing.md,
          right: GvSpacing.md,
          top: GvSpacing.md,
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(GvSpacing.sm),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                TextField(
                  controller: searchController,
                  onChanged: _scheduleSearch,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: t(
                        'Pesquisar morada ou local',
                        'Search address or place',
                        'Buscar dirección o lugar',
                        'Rechercher une adresse ou un lieu'),
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: searching
                        ? const Padding(
                            padding: EdgeInsets.all(14),
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : searchController.text.isEmpty
                            ? null
                            : IconButton(
                                tooltip:
                                    t('Limpar', 'Clear', 'Borrar', 'Effacer'),
                                onPressed: _clearSearch,
                                icon: const Icon(Icons.close),
                              ),
                  ),
                ),
                if (searchError != null)
                  Padding(
                    padding: const EdgeInsets.only(top: GvSpacing.xs),
                    child: Text(searchError!,
                        style: const TextStyle(color: GvColors.critical)),
                  ),
                if (suggestions.isNotEmpty)
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 220),
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: suggestions.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final item = suggestions[index];
                        return ListTile(
                          dense: true,
                          leading: const Icon(Icons.place_outlined),
                          title: Text(item.primaryText),
                          subtitle: item.secondaryText.isEmpty
                              ? null
                              : Text(item.secondaryText),
                          onTap: searching ? null : () => _selectPlace(item),
                        );
                      },
                    ),
                  ),
                const SizedBox(height: GvSpacing.xs),
                Text(
                  '${t('Toque no mapa para ajustar o ponto.', 'Tap the map to adjust the point.', 'Toque el mapa para ajustar el punto.', 'Touchez la carte pour ajuster le point.')} '
                  '${selected.latitude.toStringAsFixed(6)}, '
                  '${selected.longitude.toStringAsFixed(6)}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 12),
                ),
              ]),
            ),
          ),
        ),
        Positioned(
          right: GvSpacing.md,
          bottom: 54,
          child: FloatingActionButton.extended(
            heroTag: 'current-location',
            onPressed: locating ? null : _useCurrentLocation,
            icon: locating
                ? const SizedBox.square(
                    dimension: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.my_location),
            label: Text(t('Usar minha localização', 'Use my location',
                'Usar mi ubicación', 'Utiliser ma position')),
          ),
        ),
        Positioned(
          left: 8,
          bottom: 4,
          child: DecoratedBox(
            decoration: const BoxDecoration(color: Color(0xCCFFFFFF)),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
              child: Text(mapProvider.attribution,
                  style: const TextStyle(color: Colors.black87, fontSize: 10)),
            ),
          ),
        ),
      ]),
    );
  }

  void _scheduleSearch(String value) {
    searchDebounce?.cancel();
    setState(() {
      searchError = null;
      if (value.trim().length < 2) suggestions = const [];
    });
    if (value.trim().length < 2) return;
    searchDebounce = Timer(const Duration(milliseconds: 350), _search);
  }

  Future<void> _search() async {
    final query = searchController.text.trim();
    if (query.length < 2) return;
    final language = Localizations.localeOf(context).languageCode;
    setState(() => searching = true);
    try {
      final results = await ref.read(locationRepositoryProvider).autocomplete(
            query: query,
            sessionToken: searchSessionToken,
            languageCode: language,
            regionCode: widget.regionCode,
            biasLatitude: selected.latitude,
            biasLongitude: selected.longitude,
          );
      if (!mounted || query != searchController.text.trim()) return;
      setState(() => suggestions = results);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        suggestions = const [];
        searchError = '$error';
      });
    } finally {
      if (mounted) setState(() => searching = false);
    }
  }

  Future<void> _selectPlace(LocationSuggestion suggestion) async {
    searchDebounce?.cancel();
    final language = Localizations.localeOf(context).languageCode;
    setState(() => searching = true);
    try {
      final place = await ref.read(locationRepositoryProvider).resolve(
            providerReference: suggestion.providerReference,
            sessionToken: searchSessionToken,
            languageCode: language,
          );
      if (!mounted) return;
      selected = LatLng(place.latitude, place.longitude);
      searchController.text = place.formattedAddress;
      searchSessionToken = _newSessionToken();
      mapController.move(selected, 16);
      setState(() {
        suggestions = const [];
        searchError = null;
      });
    } catch (error) {
      if (mounted) setState(() => searchError = '$error');
    } finally {
      if (mounted) setState(() => searching = false);
    }
  }

  void _clearSearch() {
    searchDebounce?.cancel();
    searchController.clear();
    setState(() {
      suggestions = const [];
      searchError = null;
      searchSessionToken = _newSessionToken();
    });
  }

  String _newSessionToken() {
    final random = Random.secure();
    return List.generate(
      16,
      (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
    ).join();
  }

  Future<void> _useCurrentLocation() async {
    setState(() => locating = true);
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw StateError(_t(
            'Ative os serviços de localização do dispositivo.',
            'Enable location services on the device.',
            'Active los servicios de ubicación del dispositivo.',
            'Activez les services de localisation de l’appareil.'));
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied) {
        throw StateError(_t(
            'A permissão de localização foi recusada.',
            'Location permission was denied.',
            'Se rechazó el permiso de ubicación.',
            'L’autorisation de localisation a été refusée.'));
      }
      if (permission == LocationPermission.deniedForever) {
        throw StateError(_t(
            'Autorize a localização nas Definições do dispositivo.',
            'Allow location access in the device Settings.',
            'Autorice la ubicación en los Ajustes del dispositivo.',
            'Autorisez la localisation dans les réglages de l’appareil.'));
      }
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 20),
        ),
      );
      selected = LatLng(position.latitude, position.longitude);
      mapController.move(selected, 17);
      if (mounted) setState(() {});
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('$error')));
    } finally {
      if (mounted) setState(() => locating = false);
    }
  }
}
