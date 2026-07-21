import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_spacing.dart';
import '../data/sites_repository.dart';
import '../domain/sector.dart';

class NewSiteScreen extends ConsumerStatefulWidget {
  const NewSiteScreen({super.key});

  @override
  ConsumerState<NewSiteScreen> createState() => _NewSiteScreenState();
}

class _NewSiteScreenState extends ConsumerState<NewSiteScreen> {
  final formKey = GlobalKey<FormState>();
  final name = TextEditingController();
  final country = TextEditingController(text: 'Angola');
  final province = TextEditingController();
  final municipality = TextEditingController();
  final area = TextEditingController();
  final latitude = TextEditingController();
  final longitude = TextEditingController();
  Sector sector = Sector.agriculture;
  bool submitting = false;

  @override
  void dispose() {
    for (final controller in [
      name,
      country,
      province,
      municipality,
      area,
      latitude,
      longitude,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  double? _number(TextEditingController controller) {
    final value = controller.text.trim().replaceAll(',', '.');
    return value.isEmpty ? null : double.tryParse(value);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Adicionar local')),
        body: Form(
          key: formKey,
          child: ListView(
            padding: const EdgeInsets.all(GvSpacing.lg),
            children: [
              const Text(
                'Registe uma fazenda, exploração, mina, infraestrutura ou área ambiental da sua organização.',
              ),
              const SizedBox(height: GvSpacing.lg),
              TextFormField(
                controller: name,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Nome do local *',
                  prefixIcon: Icon(Icons.business_outlined),
                ),
                validator: (value) => (value?.trim().length ?? 0) < 2
                    ? 'Introduza pelo menos 2 caracteres.'
                    : null,
              ),
              const SizedBox(height: GvSpacing.md),
              DropdownButtonFormField<Sector>(
                initialValue: sector,
                decoration: const InputDecoration(
                  labelText: 'Setor',
                  prefixIcon: Icon(Icons.category_outlined),
                ),
                items: Sector.values
                    .map((value) => DropdownMenuItem(
                          value: value,
                          child: Text(value.label),
                        ))
                    .toList(),
                onChanged: (value) => setState(() => sector = value!),
              ),
              const SizedBox(height: GvSpacing.md),
              TextFormField(
                controller: country,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(labelText: 'País *'),
                validator: (value) => (value?.trim().length ?? 0) < 2
                    ? 'Introduza o país.'
                    : null,
              ),
              const SizedBox(height: GvSpacing.md),
              Row(children: [
                Expanded(
                  child: TextFormField(
                    controller: province,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Província'),
                  ),
                ),
                const SizedBox(width: GvSpacing.sm),
                Expanded(
                  child: TextFormField(
                    controller: municipality,
                    textInputAction: TextInputAction.next,
                    decoration: const InputDecoration(labelText: 'Município'),
                  ),
                ),
              ]),
              const SizedBox(height: GvSpacing.md),
              TextFormField(
                controller: area,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration:
                    const InputDecoration(labelText: 'Área estimada (ha)'),
                validator: (value) {
                  if (value == null || value.trim().isEmpty) return null;
                  final parsed = _number(area);
                  return parsed == null || parsed <= 0
                      ? 'Introduza uma área válida.'
                      : null;
                },
              ),
              const SizedBox(height: GvSpacing.lg),
              const Text('Localização no mapa (opcional)',
                  style: TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: GvSpacing.xs),
              const Text(
                'Pode adicionar as coordenadas agora ou delimitar a propriedade no mapa mais tarde.',
                style: TextStyle(fontSize: 12),
              ),
              const SizedBox(height: GvSpacing.sm),
              Row(children: [
                Expanded(
                  child: TextFormField(
                    controller: latitude,
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true, signed: true),
                    decoration: const InputDecoration(labelText: 'Latitude'),
                    validator: (_) {
                      final parsed = _number(latitude);
                      return parsed != null && (parsed < -90 || parsed > 90)
                          ? 'Entre -90 e 90.'
                          : null;
                    },
                  ),
                ),
                const SizedBox(width: GvSpacing.sm),
                Expanded(
                  child: TextFormField(
                    controller: longitude,
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true, signed: true),
                    decoration: const InputDecoration(labelText: 'Longitude'),
                    validator: (_) {
                      final parsed = _number(longitude);
                      return parsed != null && (parsed < -180 || parsed > 180)
                          ? 'Entre -180 e 180.'
                          : null;
                    },
                  ),
                ),
              ]),
              const SizedBox(height: GvSpacing.xl),
              FilledButton.icon(
                onPressed: submitting ? null : _submit,
                icon: submitting
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.add_location_alt_outlined),
                label: Text(submitting ? 'A adicionar…' : 'Adicionar local'),
              ),
            ],
          ),
        ),
      );

  Future<void> _submit() async {
    if (!formKey.currentState!.validate()) return;
    setState(() => submitting = true);
    try {
      final site = await ref.read(sitesRepositoryProvider).createSite(
            name: name.text,
            sector: sector,
            country: country.text,
            province: province.text.isEmpty ? null : province.text,
            municipality: municipality.text.isEmpty ? null : municipality.text,
            areaHectares: _number(area),
            latitude: _number(latitude),
            longitude: _number(longitude),
          );
      ref.invalidate(sitesProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${site.name} foi adicionado.')),
      );
      context.go('/sites/${site.id}');
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Não foi possível adicionar o local: $error')),
      );
    } finally {
      if (mounted) setState(() => submitting = false);
    }
  }
}
