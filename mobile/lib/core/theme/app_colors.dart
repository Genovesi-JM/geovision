import 'package:flutter/material.dart';

/// GeoVision brand palette, translated from the geovisionops.com design system
/// (dark operational aesthetic, cyan/blue/green accents, Inter typography).
abstract final class GvColors {
  // Backgrounds — matched to the website tokens in assets/css/public-shell.css
  // (--bg-darker/--bg-dark/--bg-card/--bg-surface).
  static const bgDarker = Color(0xFF020408);
  static const bgDark = Color(0xFF050914);
  static const surface = Color(0xFF0F172A); // --bg-card base (slate-900)
  static const surfaceRaised = Color(0xFF1E293B); // --bg-surface base (slate-800)
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

  // Slate-tinted hairline to match the website's --border rgba(148,163,184,0.12).
  static const border = Color(0x1F94A3B8);
  static const borderStrong = Color(0x3D94A3B8);

  static const gradientCard = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF0F172A), Color(0xFF0B1220)],
  );

  // Primary brand gradient — the website's --gradient-primary (green → blue,
  // 135deg). This is the signature CTA/logo gradient.
  static const gradientAccent = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [accentGreen, accentBlue],
  );
}
