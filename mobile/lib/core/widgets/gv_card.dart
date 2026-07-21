import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// The canonical GeoVision surface: gradient panel, hairline border, rounded
/// corners — the mobile translation of the website's card language.
class GvCard extends StatelessWidget {
  const GvCard({super.key, required this.child, this.padding, this.onTap});
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final content = Container(
      padding: padding ?? const EdgeInsets.all(GvSpacing.lg),
      decoration: BoxDecoration(
        gradient: GvColors.gradientCard,
        borderRadius: BorderRadius.circular(GvSpacing.radiusLg),
        border: Border.all(color: GvColors.border),
      ),
      child: child,
    );
    if (onTap == null) return content;
    return InkWell(
      borderRadius: BorderRadius.circular(GvSpacing.radiusLg),
      onTap: onTap,
      child: content,
    );
  }
}
