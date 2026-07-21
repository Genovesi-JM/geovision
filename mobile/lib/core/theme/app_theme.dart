import 'package:flutter/material.dart';
import 'app_colors.dart';
import 'app_spacing.dart';

/// The GeoVision mobile theme. Brand policy is dark-first (the operational
/// platform mirrors the website's dark aesthetic); a light theme hook is
/// reserved for a future accessibility toggle.
abstract final class GvTheme {
  static ThemeData dark() {
    const scheme = ColorScheme.dark(
      primary: GvColors.accentCyan,
      secondary: GvColors.accentBlue,
      surface: GvColors.surface,
      error: GvColors.critical,
      onPrimary: GvColors.bgDarker,
      onSurface: GvColors.textPrimary,
    );

    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: GvColors.bgDark,
      fontFamily: 'Inter',
      splashFactory: InkRipple.splashFactory,
    );

    return base.copyWith(
      textTheme: _textTheme(base.textTheme),
      appBarTheme: const AppBarTheme(
        backgroundColor: GvColors.bgDark,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          fontFamily: 'Inter',
          fontSize: 18,
          fontWeight: FontWeight.w700,
          color: GvColors.textPrimary,
        ),
      ),
      cardTheme: CardThemeData(
        color: GvColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(GvSpacing.radiusLg),
          side: const BorderSide(color: GvColors.border),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: GvColors.surfaceDeep,
        indicatorColor: GvColors.accentCyan.withValues(alpha: 0.16),
        labelTextStyle: WidgetStateProperty.all(
          const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: GvColors.surfaceDeep,
        hintStyle: const TextStyle(color: GvColors.textMuted),
        contentPadding: const EdgeInsets.symmetric(
            horizontal: GvSpacing.lg, vertical: GvSpacing.md),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
          borderSide: const BorderSide(color: GvColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
          borderSide: const BorderSide(color: GvColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
          borderSide: const BorderSide(color: GvColors.accentCyan),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: GvColors.accentCyan,
          foregroundColor: GvColors.bgDarker,
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
          padding: const EdgeInsets.symmetric(
              horizontal: GvSpacing.xl, vertical: GvSpacing.md),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(GvSpacing.radiusPill),
          ),
        ),
      ),
      dividerTheme:
          const DividerThemeData(color: GvColors.border, thickness: 1),
    );
  }

  static TextTheme _textTheme(TextTheme t) => t.apply(
        fontFamily: 'Inter',
        bodyColor: GvColors.textPrimary,
        displayColor: GvColors.textPrimary,
      );
}
