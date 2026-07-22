import 'package:flutter/material.dart';

import '../../../core/theme/app_colors.dart';
import '../domain/product.dart';

class ProductImage extends StatelessWidget {
  const ProductImage({
    required this.product,
    this.borderRadius = BorderRadius.zero,
    this.fit = BoxFit.cover,
    super.key,
  });

  final GvProduct product;
  final BorderRadius borderRadius;
  final BoxFit fit;

  IconData get _fallbackIcon => switch (product.category) {
        'seeds' => Icons.grass,
        'inputs' => Icons.science_outlined,
        'equipment' => Icons.agriculture,
        'hardware' => Icons.sensors,
        'service' => Icons.flight_takeoff,
        'subscription' => Icons.dashboard_customize_outlined,
        _ => Icons.inventory_2_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final image = product.image;
    return ClipRRect(
      borderRadius: borderRadius,
      child: image == null || image.isEmpty
          ? _fallback()
          : image.startsWith('https://')
              ? Image.network(
                  image,
                  fit: fit,
                  width: double.infinity,
                  height: double.infinity,
                  errorBuilder: (_, __, ___) => _fallback(),
                )
              : Image.asset(
                  image,
                  fit: fit,
                  width: double.infinity,
                  height: double.infinity,
                  errorBuilder: (_, __, ___) => _fallback(),
                ),
    );
  }

  Widget _fallback() => DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              GvColors.accentGreen.withValues(alpha: .25),
              GvColors.surfaceDeep,
            ],
          ),
        ),
        child: Center(
          child: Icon(_fallbackIcon, size: 56, color: GvColors.accentGreen),
        ),
      );
}
