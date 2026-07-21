import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../domain/help_guide.dart';

class GuidesScreen extends StatefulWidget {
  const GuidesScreen({super.key});

  @override
  State<GuidesScreen> createState() => _GuidesScreenState();
}

class _GuidesScreenState extends State<GuidesScreen> {
  GuideCategory? category;
  String query = '';

  @override
  Widget build(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    final copy = _GuideCopy(language);
    final rows = helpGuides.where((guide) {
      final matchesCategory = category == null || guide.category == category;
      final needle = query.toLowerCase();
      final matchesQuery = needle.isEmpty ||
          guideText(guide.title, language).toLowerCase().contains(needle) ||
          guideText(guide.summary, language).toLowerCase().contains(needle);
      return matchesCategory && matchesQuery;
    }).toList();
    return Scaffold(
      appBar: AppBar(title: Text(copy.title)),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          Container(
            padding: const EdgeInsets.all(GvSpacing.lg),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: [Color(0xFF064E3B), Color(0xFF0B1428)]),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(children: [
              const Icon(Icons.menu_book_outlined,
                  size: 42, color: GvColors.accentGreen),
              const SizedBox(width: GvSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(copy.hero,
                        style: const TextStyle(
                            fontSize: 18, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 4),
                    Text(copy.subtitle,
                        style: const TextStyle(
                            color: GvColors.textSecondary, fontSize: 12)),
                  ],
                ),
              ),
            ]),
          ),
          const SizedBox(height: GvSpacing.md),
          TextField(
            onChanged: (value) => setState(() => query = value.trim()),
            decoration: InputDecoration(
              hintText: copy.search,
              prefixIcon: const Icon(Icons.search),
            ),
          ),
          const SizedBox(height: GvSpacing.sm),
          SizedBox(
            height: 38,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                _chip(copy.all, null),
                for (final value in GuideCategory.values)
                  _chip(copy.category(value), value),
              ],
            ),
          ),
          const SizedBox(height: GvSpacing.md),
          ...rows.map((guide) => Padding(
                padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                child: GvCard(
                  onTap: () => context.go('/guides/${guide.id}'),
                  child: Row(children: [
                    Container(
                      width: 52,
                      height: 52,
                      decoration: BoxDecoration(
                        color: GvColors.accentCyan.withValues(alpha: .14),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Icon(guide.icon, color: GvColors.accentCyan),
                    ),
                    const SizedBox(width: GvSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(guideText(guide.title, language),
                              style:
                                  const TextStyle(fontWeight: FontWeight.w800)),
                          const SizedBox(height: 3),
                          Text(guideText(guide.summary, language),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  color: GvColors.textSecondary, fontSize: 12)),
                          const SizedBox(height: 5),
                          Text(
                              '${guide.minutes} min · ${guide.steps.length} ${copy.steps}',
                              style: const TextStyle(
                                  color: GvColors.textMuted, fontSize: 10)),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right, color: GvColors.textMuted),
                  ]),
                ),
              )),
        ],
      ),
    );
  }

  Widget _chip(String label, GuideCategory? value) => Padding(
        padding: const EdgeInsets.only(right: 7),
        child: ChoiceChip(
          label: Text(label),
          selected: category == value,
          onSelected: (_) => setState(() => category = value),
        ),
      );
}

class GuideDetailScreen extends StatelessWidget {
  const GuideDetailScreen({required this.guideId, super.key});
  final String guideId;

  @override
  Widget build(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    final copy = _GuideCopy(language);
    final guide = helpGuides.where((row) => row.id == guideId).firstOrNull;
    if (guide == null) {
      return Scaffold(body: Center(child: Text(copy.notFound)));
    }
    return Scaffold(
      appBar: AppBar(title: Text(guideText(guide.title, language))),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          Icon(guide.icon, size: 68, color: GvColors.accentCyan),
          const SizedBox(height: GvSpacing.md),
          Text(guideText(guide.title, language),
              textAlign: TextAlign.center,
              style:
                  const TextStyle(fontSize: 23, fontWeight: FontWeight.w900)),
          const SizedBox(height: 6),
          Text(guideText(guide.summary, language),
              textAlign: TextAlign.center,
              style: const TextStyle(color: GvColors.textSecondary)),
          if (guide.warning != null) ...[
            const SizedBox(height: GvSpacing.lg),
            Container(
              padding: const EdgeInsets.all(GvSpacing.md),
              decoration: BoxDecoration(
                color: GvColors.high.withValues(alpha: .13),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: GvColors.high.withValues(alpha: .5)),
              ),
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(Icons.warning_amber_rounded, color: GvColors.high),
                const SizedBox(width: 10),
                Expanded(child: Text(guideText(guide.warning!, language))),
              ]),
            ),
          ],
          const SizedBox(height: GvSpacing.xl),
          for (var index = 0; index < guide.steps.length; index++)
            _VisualStep(
              number: index + 1,
              step: guide.steps[index],
              language: language,
              last: index == guide.steps.length - 1,
            ),
          if (guide.requiresTechnician) ...[
            const SizedBox(height: GvSpacing.md),
            FilledButton.icon(
              onPressed: () => context.go('/work/new'),
              icon: const Icon(Icons.support_agent),
              label: Text(copy.requestTechnician),
            ),
          ],
        ],
      ),
    );
  }
}

class _VisualStep extends StatelessWidget {
  const _VisualStep(
      {required this.number,
      required this.step,
      required this.language,
      required this.last});
  final int number;
  final GuideStep step;
  final String language;
  final bool last;
  @override
  Widget build(BuildContext context) => IntrinsicHeight(
        child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(
            width: 48,
            child: Column(children: [
              CircleAvatar(
                backgroundColor: GvColors.accentGreen,
                child: Text('$number',
                    style: const TextStyle(
                        color: Colors.black, fontWeight: FontWeight.w900)),
              ),
              if (!last)
                Expanded(
                  child: Container(width: 2, color: GvColors.borderStrong),
                ),
            ]),
          ),
          const SizedBox(width: GvSpacing.sm),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: GvSpacing.lg),
              child: GvCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(step.icon, color: GvColors.accentCyan, size: 28),
                    const SizedBox(height: 8),
                    Text(guideText(step.title, language),
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w800)),
                    const SizedBox(height: 5),
                    Text(guideText(step.body, language),
                        style: const TextStyle(
                            color: GvColors.textSecondary, height: 1.4)),
                  ],
                ),
              ),
            ),
          ),
        ]),
      );
}

class _GuideCopy {
  const _GuideCopy(this.language);
  final String language;
  String t(String pt, String en, String es, String fr) =>
      switch (language) { 'pt' => pt, 'es' => es, 'fr' => fr, _ => en };
  String get title =>
      t('Guias visuais', 'Visual guides', 'Guías visuales', 'Guides visuels');
  String get hero => t('Aprenda com segurança', 'Learn safely',
      'Aprenda con seguridad', 'Apprenez en sécurité');
  String get subtitle => t(
      'Instalação, uso, manutenção e interpretação — disponível offline.',
      'Installation, use, maintenance and interpretation — available offline.',
      'Instalación, uso, mantenimiento e interpretación — sin conexión.',
      'Installation, usage, maintenance et interprétation — hors ligne.');
  String get search => t('Pesquisar guia…', 'Search guides…', 'Buscar guía…',
      'Rechercher un guide…');
  String get all => t('Todos', 'All', 'Todos', 'Tous');
  String get steps => t('passos', 'steps', 'pasos', 'étapes');
  String get notFound => t('Guia não encontrado.', 'Guide not found.',
      'Guía no encontrada.', 'Guide introuvable.');
  String get requestTechnician => t(
      'Solicitar técnico GeoVision',
      'Request a GeoVision technician',
      'Solicitar técnico GeoVision',
      'Demander un technicien GeoVision');
  String category(GuideCategory value) => switch (value) {
        GuideCategory.devices =>
          t('Dispositivos', 'Devices', 'Dispositivos', 'Appareils'),
        GuideCategory.equipment =>
          t('Equipamentos', 'Equipment', 'Equipos', 'Équipements'),
        GuideCategory.app => t('Aplicação', 'App', 'Aplicación', 'Application'),
        GuideCategory.insights => t('Alertas & KPIs', 'Alerts & KPIs',
            'Alertas y KPI', 'Alertes et KPI'),
        GuideCategory.safety =>
          t('Segurança', 'Safety', 'Seguridad', 'Sécurité'),
      };
}
