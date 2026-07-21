import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_states.dart';
import '../../alerts/data/alerts_repository.dart';
import '../../sites/data/sites_repository.dart';
import '../../sites/domain/site.dart';

/// Credential-free operational map. With the demo provider the site boundary,
/// field polygons, alert markers and device markers are painted on a local
/// canvas — real providers (Mapbox/ArcGIS) plug in behind MapProvider.
class SiteMapScreen extends ConsumerStatefulWidget {
  const SiteMapScreen({super.key, required this.siteId});
  final String siteId;
  @override
  ConsumerState<SiteMapScreen> createState() => _SiteMapScreenState();
}

class _SiteMapScreenState extends ConsumerState<SiteMapScreen> {
  final _layers = <String, bool>{};
  String? _tappedInfo;

  @override
  Widget build(BuildContext context) {
    final siteAsync = ref.watch(siteDetailProvider(widget.siteId));
    final alertsAsync = ref.watch(alertsProvider);
    final mapProvider = ref.watch(mapProviderProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Site map'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: GvSpacing.md),
            child: Center(
              child: Text(
                  mapProvider.requiresCredentials ? mapProvider.id : 'demo',
                  style:
                      const TextStyle(color: GvColors.textMuted, fontSize: 11)),
            ),
          ),
        ],
      ),
      body: siteAsync.when(
        loading: () => const GvLoading(),
        error: (e, _) => GvErrorState(message: '$e'),
        data: (site) {
          if (site == null) return const GvEmpty(message: 'Site not found.');
          final layerDefs = mapProvider.layersForSite(site);
          for (final l in layerDefs) {
            _layers.putIfAbsent(l.id, () => l.enabledByDefault);
          }
          final alerts = alertsAsync.value?.value
                  .where((a) => a.siteId == site.id && a.lat != null)
                  .toList() ??
              [];

          return Column(
            children: [
              Expanded(
                child: GestureDetector(
                  onTapDown: (d) => setState(() => _tappedInfo =
                      'Feature at (${d.localPosition.dx.toInt()}, ${d.localPosition.dy.toInt()})'),
                  child: Container(
                    color: GvColors.surfaceDeep,
                    child: CustomPaint(
                      painter: _SiteMapPainter(
                        site: site,
                        showBoundary: _layers['boundary'] ?? true,
                        showFields: _layers['fields'] ?? true,
                        showNdvi: _layers['ndvi'] ?? true,
                        showAlerts:
                            (_layers['alerts'] ?? true) && alerts.isNotEmpty,
                        alertCount: alerts.length,
                      ),
                      child: const SizedBox.expand(),
                    ),
                  ),
                ),
              ),
              if (_tappedInfo != null)
                Container(
                  width: double.infinity,
                  color: GvColors.surface,
                  padding: const EdgeInsets.all(GvSpacing.md),
                  child: Text('Tap-to-inspect: $_tappedInfo',
                      style: const TextStyle(
                          color: GvColors.textSecondary, fontSize: 12)),
                ),
              _LayerBar(
                defs: layerDefs.map((l) => l.name).toList(),
                values: layerDefs.map((l) => _layers[l.id] ?? false).toList(),
                onToggle: (i) => setState(() {
                  final id = layerDefs[i].id;
                  _layers[id] = !(_layers[id] ?? false);
                }),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _LayerBar extends StatelessWidget {
  const _LayerBar(
      {required this.defs, required this.values, required this.onToggle});
  final List<String> defs;
  final List<bool> values;
  final void Function(int) onToggle;
  @override
  Widget build(BuildContext context) {
    return Container(
      color: GvColors.bgDarker,
      padding: const EdgeInsets.symmetric(
          horizontal: GvSpacing.md, vertical: GvSpacing.sm),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (var i = 0; i < defs.length; i++)
              Padding(
                padding: const EdgeInsets.only(right: GvSpacing.sm),
                child: FilterChip(
                  label: Text(defs[i], style: const TextStyle(fontSize: 11)),
                  selected: values[i],
                  onSelected: (_) => onToggle(i),
                  selectedColor: GvColors.accentCyan.withValues(alpha: 0.2),
                  backgroundColor: GvColors.surfaceDeep,
                  side: const BorderSide(color: GvColors.border),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _SiteMapPainter extends CustomPainter {
  _SiteMapPainter({
    required this.site,
    required this.showBoundary,
    required this.showFields,
    required this.showNdvi,
    required this.showAlerts,
    required this.alertCount,
  });
  final Site site;
  final bool showBoundary;
  final bool showFields;
  final bool showNdvi;
  final bool showAlerts;
  final int alertCount;

  @override
  void paint(Canvas canvas, Size size) {
    final grid = Paint()
      ..color = GvColors.border
      ..strokeWidth = 1;
    for (double x = 0; x < size.width; x += 40) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), grid);
    }
    for (double y = 0; y < size.height; y += 40) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), grid);
    }

    final w = size.width, h = size.height;
    final boundaryRect = Rect.fromLTWH(w * 0.12, h * 0.12, w * 0.76, h * 0.72);

    if (showNdvi) {
      final ndvi = Paint()
        ..shader = const LinearGradient(colors: [
          Color(0x3322C55E),
          Color(0x330EA5E9),
        ]).createShader(boundaryRect);
      canvas.drawRRect(
          RRect.fromRectAndRadius(boundaryRect, const Radius.circular(8)),
          ndvi);
    }

    if (showFields) {
      final fieldPaint = Paint()
        ..color = GvColors.accentGreen.withValues(alpha: 0.18)
        ..style = PaintingStyle.fill;
      final fieldBorder = Paint()
        ..color = GvColors.accentGreen
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5;
      final n = site.areas.isEmpty ? 3 : site.areas.length;
      final cellW = boundaryRect.width / n;
      for (var i = 0; i < n; i++) {
        final r = Rect.fromLTWH(boundaryRect.left + i * cellW + 4,
            boundaryRect.top + 8, cellW - 8, boundaryRect.height - 16);
        canvas.drawRRect(
            RRect.fromRectAndRadius(r, const Radius.circular(6)), fieldPaint);
        canvas.drawRRect(
            RRect.fromRectAndRadius(r, const Radius.circular(6)), fieldBorder);
      }
    }

    if (showBoundary) {
      final b = Paint()
        ..color = GvColors.accentCyan
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5;
      canvas.drawRRect(
          RRect.fromRectAndRadius(boundaryRect, const Radius.circular(8)), b);
    }

    if (showAlerts) {
      final marker = Paint()..color = GvColors.critical;
      for (var i = 0; i < alertCount; i++) {
        final dx = boundaryRect.left +
            boundaryRect.width * (0.3 + 0.4 * (i / (alertCount)));
        final dy = boundaryRect.top + boundaryRect.height * (0.4 + 0.15 * i);
        canvas.drawCircle(Offset(dx, dy), 7, marker);
        canvas.drawCircle(
            Offset(dx, dy),
            12,
            Paint()
              ..color = GvColors.critical.withValues(alpha: 0.3)
              ..style = PaintingStyle.stroke
              ..strokeWidth = 2);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _SiteMapPainter old) =>
      old.showBoundary != showBoundary ||
      old.showFields != showFields ||
      old.showNdvi != showNdvi ||
      old.showAlerts != showAlerts;
}
