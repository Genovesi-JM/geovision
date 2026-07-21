import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../data/sites_repository.dart';
import '../domain/angola_locations.dart';
import '../domain/sector.dart';
import '../domain/site.dart';
import 'location_picker_screen.dart';

class NewSiteScreen extends ConsumerStatefulWidget {
  const NewSiteScreen({super.key});

  @override
  ConsumerState<NewSiteScreen> createState() => _NewSiteScreenState();
}

class _NewSiteScreenState extends ConsumerState<NewSiteScreen> {
  final formKey = GlobalKey<FormState>();
  final name = TextEditingController();
  final area = TextEditingController();
  Sector sector = Sector.agriculture;
  String country = supportedSiteCountries.first;
  String? province;
  String? municipality;
  GeoPoint? location;
  bool submitting = false;

  @override
  void dispose() {
    name.dispose();
    area.dispose();
    super.dispose();
  }

  double? get parsedArea {
    final value = area.text.trim().replaceAll(',', '.');
    return value.isEmpty ? null : double.tryParse(value);
  }

  @override
  Widget build(BuildContext context) {
    final copy = _SiteFormCopy.of(context);
    final municipalities = province == null
        ? const <String>[]
        : angolaMunicipalities[province!] ?? const <String>[];
    return Scaffold(
      appBar: AppBar(title: Text(copy.title)),
      body: Form(
        key: formKey,
        child: ListView(
          padding: const EdgeInsets.all(GvSpacing.lg),
          children: [
            Text(copy.intro),
            const SizedBox(height: GvSpacing.lg),
            TextFormField(
              controller: name,
              textInputAction: TextInputAction.next,
              decoration: InputDecoration(
                labelText: copy.name,
                prefixIcon: const Icon(Icons.business_outlined),
              ),
              validator: (value) =>
                  (value?.trim().length ?? 0) < 2 ? copy.nameValidation : null,
            ),
            const SizedBox(height: GvSpacing.md),
            DropdownButtonFormField<Sector>(
              initialValue: sector,
              decoration: InputDecoration(
                labelText: copy.sector,
                prefixIcon: const Icon(Icons.category_outlined),
              ),
              items: Sector.values
                  .map((value) => DropdownMenuItem(
                        value: value,
                        child: Text(copy.sectorName(value)),
                      ))
                  .toList(),
              onChanged: (value) => setState(() => sector = value!),
            ),
            const SizedBox(height: GvSpacing.md),
            DropdownButtonFormField<String>(
              initialValue: country,
              decoration: InputDecoration(
                labelText: copy.country,
                prefixIcon: const Icon(Icons.public),
              ),
              items: supportedSiteCountries
                  .map((value) =>
                      DropdownMenuItem(value: value, child: Text(value)))
                  .toList(),
              onChanged: (value) => setState(() {
                country = value!;
                province = null;
                municipality = null;
              }),
            ),
            const SizedBox(height: GvSpacing.md),
            DropdownButtonFormField<String>(
              key: ValueKey(province),
              initialValue: province,
              isExpanded: true,
              decoration: InputDecoration(labelText: copy.province),
              items: angolaMunicipalities.keys
                  .map((value) =>
                      DropdownMenuItem(value: value, child: Text(value)))
                  .toList(),
              onChanged: (value) => setState(() {
                province = value;
                municipality = null;
              }),
              validator: (value) => value == null ? copy.requiredField : null,
            ),
            const SizedBox(height: GvSpacing.md),
            DropdownButtonFormField<String>(
              key: ValueKey('$province-$municipality'),
              initialValue: municipality,
              isExpanded: true,
              decoration: InputDecoration(labelText: copy.municipality),
              items: municipalities
                  .map((value) =>
                      DropdownMenuItem(value: value, child: Text(value)))
                  .toList(),
              onChanged: province == null
                  ? null
                  : (value) => setState(() => municipality = value),
              validator: (value) => value == null ? copy.requiredField : null,
            ),
            const SizedBox(height: GvSpacing.md),
            TextFormField(
              controller: area,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: copy.area),
              validator: (value) {
                if (value == null || value.trim().isEmpty) return null;
                return parsedArea == null || parsedArea! <= 0
                    ? copy.areaValidation
                    : null;
              },
            ),
            const SizedBox(height: GvSpacing.lg),
            Text(copy.mapTitle,
                style: const TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: GvSpacing.xs),
            Text(copy.mapHelp, style: const TextStyle(fontSize: 12)),
            const SizedBox(height: GvSpacing.sm),
            OutlinedButton.icon(
              onPressed: _pickLocation,
              icon: Icon(
                  location == null ? Icons.map_outlined : Icons.location_on),
              label: Text(location == null
                  ? copy.chooseOnMap
                  : '${location!.lat.toStringAsFixed(6)}, '
                      '${location!.lng.toStringAsFixed(6)}'),
            ),
            if (location != null)
              TextButton.icon(
                onPressed: () => setState(() => location = null),
                icon: const Icon(Icons.close, size: 18),
                label: Text(copy.removeLocation),
              ),
            const SizedBox(height: GvSpacing.xl),
            FilledButton.icon(
              onPressed: submitting ? null : _submit,
              icon: submitting
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.add_location_alt_outlined),
              label: Text(submitting ? copy.adding : copy.title),
            ),
            const SizedBox(height: GvSpacing.sm),
            Row(children: [
              const Icon(Icons.verified_user_outlined,
                  size: 16, color: GvColors.accentGreen),
              const SizedBox(width: 6),
              Expanded(
                child: Text(copy.privacy, style: const TextStyle(fontSize: 11)),
              ),
            ]),
          ],
        ),
      ),
    );
  }

  Future<void> _pickLocation() async {
    final result = await Navigator.of(context).push<GeoPoint>(
      MaterialPageRoute(
        builder: (_) => LocationPickerScreen(initial: location),
      ),
    );
    if (result != null && mounted) setState(() => location = result);
  }

  Future<void> _submit() async {
    if (!formKey.currentState!.validate()) return;
    final copy = _SiteFormCopy.of(context);
    setState(() => submitting = true);
    try {
      final site = await ref.read(sitesRepositoryProvider).createSite(
            name: name.text,
            sector: sector,
            country: country,
            province: province,
            municipality: municipality,
            areaHectares: parsedArea,
            latitude: location?.lat,
            longitude: location?.lng,
          );
      ref.invalidate(sitesProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(copy.added(site.name))),
      );
      context.go('/sites/${site.id}');
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(copy.failure('$error'))),
      );
    } finally {
      if (mounted) setState(() => submitting = false);
    }
  }
}

class _SiteFormCopy {
  const _SiteFormCopy(this.language);
  final String language;
  static _SiteFormCopy of(BuildContext context) =>
      _SiteFormCopy(Localizations.localeOf(context).languageCode);

  String _pick(String pt, String en, String es, String fr) =>
      switch (language) {
        'pt' => pt,
        'es' => es,
        'fr' => fr,
        _ => en,
      };

  String get title =>
      _pick('Adicionar local', 'Add site', 'Añadir sitio', 'Ajouter un site');
  String get intro => _pick(
      'Registe uma fazenda, exploração, mina, infraestrutura ou área ambiental da sua organização.',
      'Register a farm, operation, mine, infrastructure or environmental area belonging to your organisation.',
      'Registre una finca, operación, mina, infraestructura o área ambiental de su organización.',
      'Enregistrez une ferme, exploitation, mine, infrastructure ou zone environnementale de votre organisation.');
  String get name => _pick(
      'Nome do local *', 'Site name *', 'Nombre del sitio *', 'Nom du site *');
  String get nameValidation => _pick(
      'Introduza pelo menos 2 caracteres.',
      'Enter at least 2 characters.',
      'Introduzca al menos 2 caracteres.',
      'Saisissez au moins 2 caractères.');
  String get sector => _pick('Setor', 'Sector', 'Sector', 'Secteur');
  String get country => _pick('País', 'Country', 'País', 'Pays');
  String get province =>
      _pick('Província *', 'Province *', 'Provincia *', 'Province *');
  String get municipality =>
      _pick('Município *', 'Municipality *', 'Municipio *', 'Municipalité *');
  String get requiredField => _pick('Selecione uma opção.', 'Select an option.',
      'Seleccione una opción.', 'Sélectionnez une option.');
  String get area => _pick('Área estimada (ha)', 'Estimated area (ha)',
      'Área estimada (ha)', 'Surface estimée (ha)');
  String get areaValidation => _pick(
      'Introduza uma área válida.',
      'Enter a valid area.',
      'Introduzca un área válida.',
      'Saisissez une surface valide.');
  String get mapTitle => _pick('Localização precisa', 'Precise location',
      'Ubicación precisa', 'Localisation précise');
  String get mapHelp => _pick(
      'Escolha o ponto no mapa ou autorize o uso da localização atual do dispositivo.',
      'Choose a point on the map or allow access to the device’s current location.',
      'Elija un punto en el mapa o permita el acceso a la ubicación actual del dispositivo.',
      'Choisissez un point sur la carte ou autorisez l’accès à la position actuelle de l’appareil.');
  String get chooseOnMap => _pick('Escolher no mapa', 'Choose on map',
      'Elegir en el mapa', 'Choisir sur la carte');
  String get removeLocation => _pick('Remover localização', 'Remove location',
      'Eliminar ubicación', 'Supprimer la localisation');
  String get adding => _pick('A adicionar…', 'Adding…', 'Añadiendo…', 'Ajout…');
  String get privacy => _pick(
      'A localização só é pedida quando tocar em “Usar minha localização”.',
      'Location permission is requested only when you tap “Use my location”.',
      'El permiso solo se solicita al pulsar «Usar mi ubicación».',
      'L’autorisation est demandée uniquement après « Utiliser ma position ».');
  String added(String name) => _pick('$name foi adicionado.',
      '$name was added.', '$name fue añadido.', '$name a été ajouté.');
  String failure(String error) => _pick(
      'Não foi possível adicionar o local: $error',
      'Could not add the site: $error',
      'No se pudo añadir el sitio: $error',
      'Impossible d’ajouter le site : $error');

  String sectorName(Sector value) => switch (value) {
        Sector.agriculture =>
          _pick('Agricultura', 'Agriculture', 'Agricultura', 'Agriculture'),
        Sector.livestock =>
          _pick('Pecuária', 'Livestock', 'Ganadería', 'Élevage'),
        Sector.infrastructure => _pick('Infraestruturas', 'Infrastructure',
            'Infraestructuras', 'Infrastructures'),
        Sector.mining => _pick('Mineração', 'Mining', 'Minería', 'Mines'),
        Sector.environment =>
          _pick('Ambiente', 'Environment', 'Medio ambiente', 'Environnement'),
      };
}
