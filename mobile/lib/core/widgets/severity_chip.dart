import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// GeoVision severity taxonomy: information, low, medium, high, critical.
enum Severity { information, low, medium, high, critical }

Severity severityFromString(String value) {
  switch (value.toLowerCase()) {
    case 'critical':
      return Severity.critical;
    case 'high':
      return Severity.high;
    case 'medium':
    case 'warning':
      return Severity.medium;
    case 'low':
      return Severity.low;
    default:
      return Severity.information;
  }
}

extension SeverityX on Severity {
  Color get color {
    switch (this) {
      case Severity.critical:
        return GvColors.critical;
      case Severity.high:
        return GvColors.high;
      case Severity.medium:
        return GvColors.medium;
      case Severity.low:
        return GvColors.low;
      case Severity.information:
        return GvColors.info;
    }
  }

  String get label {
    switch (this) {
      case Severity.critical:
        return 'Critical';
      case Severity.high:
        return 'High';
      case Severity.medium:
        return 'Medium';
      case Severity.low:
        return 'Low';
      case Severity.information:
        return 'Info';
    }
  }

  String localizedLabel(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    return switch ((this, language)) {
      (Severity.critical, 'pt') => 'Crítico',
      (Severity.high, 'pt') => 'Alto',
      (Severity.medium, 'pt') => 'Médio',
      (Severity.low, 'pt') => 'Baixo',
      (Severity.information, 'pt') => 'Info',
      (Severity.critical, 'es') => 'Crítica',
      (Severity.high, 'es') => 'Alta',
      (Severity.medium, 'es') => 'Media',
      (Severity.low, 'es') => 'Baja',
      (Severity.information, 'es') => 'Info',
      (Severity.critical, 'fr') => 'Critique',
      (Severity.high, 'fr') => 'Élevée',
      (Severity.medium, 'fr') => 'Moyenne',
      (Severity.low, 'fr') => 'Faible',
      (Severity.information, 'fr') => 'Info',
      _ => label,
    };
  }
}

class SeverityChip extends StatelessWidget {
  const SeverityChip(this.severity, {super.key});
  final Severity severity;

  @override
  Widget build(BuildContext context) {
    final c = severity.color;
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: GvSpacing.md, vertical: 4),
      decoration: BoxDecoration(
        color: c.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(GvSpacing.radiusPill),
        border: Border.all(color: c.withValues(alpha: 0.5)),
      ),
      child: Text(
        severity.localizedLabel(context).toUpperCase(),
        style: TextStyle(
            color: c,
            fontSize: 10,
            fontWeight: FontWeight.w800,
            letterSpacing: 0.5),
      ),
    );
  }
}
