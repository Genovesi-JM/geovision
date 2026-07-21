import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../domain/site.dart';

class LocationPickerScreen extends StatefulWidget {
  const LocationPickerScreen({super.key, this.initial});
  final GeoPoint? initial;

  @override
  State<LocationPickerScreen> createState() => _LocationPickerScreenState();
}

class _LocationPickerScreenState extends State<LocationPickerScreen> {
  final mapController = MapController();
  late LatLng selected = widget.initial == null
      ? const LatLng(-11.2027, 17.8739)
      : LatLng(widget.initial!.lat, widget.initial!.lng);
  bool locating = false;

  String _t(String pt, String en, String es, String fr) =>
      switch (Localizations.localeOf(context).languageCode) {
        'pt' => pt,
        'es' => es,
        'fr' => fr,
        _ => en,
      };

  @override
  Widget build(BuildContext context) {
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
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.geovision.geovision',
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
              child: Text(
                '${t('Toque no mapa para posicionar o local.', 'Tap the map to position the site.', 'Toque el mapa para situar el sitio.', 'Touchez la carte pour positionner le site.')}\n'
                '${selected.latitude.toStringAsFixed(6)}, '
                '${selected.longitude.toStringAsFixed(6)}',
                textAlign: TextAlign.center,
              ),
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
        const Positioned(
          left: 8,
          bottom: 4,
          child: DecoratedBox(
            decoration: BoxDecoration(color: Color(0xCCFFFFFF)),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 5, vertical: 2),
              child: Text('© OpenStreetMap contributors',
                  style: TextStyle(color: Colors.black87, fontSize: 10)),
            ),
          ),
        ),
      ]),
    );
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
