import 'package:flutter/material.dart';
import '../config/app_flavor.dart';
import '../theme/app_colors.dart';

/// A small ribbon shown in non-production builds so testers always know which
/// environment (and demo mode) they are looking at.
class EnvBanner extends StatelessWidget {
  const EnvBanner(
      {super.key,
      required this.flavor,
      required this.demoMode,
      required this.child});
  final AppFlavor flavor;
  final bool demoMode;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!flavor.showEnvironmentBanner && !demoMode) return child;
    final text = demoMode ? '${flavor.label} · DEMO DATA' : flavor.label;
    return Banner(
      message: text,
      location: BannerLocation.topEnd,
      color: GvColors.accentBlue,
      child: child,
    );
  }
}
