import 'package:flutter/material.dart';

/// GeoVision brand palette, translated from the geovisionops.com design system
/// (dark operational aesthetic, cyan/blue/green accents, Inter typography).
abstract final class GvColors {
  // Backgrounds
  static const bgDarker = Color(0xFF020408);
  static const bgDark = Color(0xFF050914);
  static const surface = Color(0xFF0B1428);
  static const surfaceRaised = Color(0xFF0F1A33);
  static const surfaceDeep = Color(0xFF020617);

  // Accents
  static const accentBlue = Color(0xFF0EA5E9);
  static const accentCyan = Color(0xFF06B6D4);
  static const accentSky = Color(0xFF38BDF8);
  static const accentGreen = Color(0xFF22C55E);

  // Text
  static const textPrimary = Color(0xFFF1F5F9);
  static const textSecondary = Color(0xFF94A3B8);
  static const textMuted = Color(0xFF64748B);

  // Semantic / severity
  static const info = Color(0xFF38BDF8);
  static const low = Color(0xFF22C55E);
  static const medium = Color(0xFFFACC15);
  static const high = Color(0xFFF97316);
  static const critical = Color(0xFFEF4444);

  static const border = Color(0x1AFFFFFF); // white @ 10%
  static const borderStrong = Color(0x33FFFFFF);

  static const gradientCard = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF0B1428), Color(0xFF081126)],
  );

  static const gradientAccent = LinearGradient(
    begin: Alignment.centerLeft,
    end: Alignment.centerRight,
    colors: [accentCyan, accentBlue],
  );
}
