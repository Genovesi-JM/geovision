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

  String get _fallbackAsset {
    if (product.sectors.contains('home')) {
      return 'assets/images/store/environmental-monitoring.jpg';
    }
    if (product.sectors.contains('mining')) {
      return 'assets/images/store/mining-drone-survey.jpg';
    }
    if (product.sectors.contains('construction')) {
      return 'assets/images/store/construction-progress.jpg';
    }
    if (product.sectors.contains('infrastructure')) {
      return 'assets/images/store/infrastructure-inspection.jpg';
    }
    if (product.sectors.contains('livestock')) {
      return 'assets/images/store/livestock-aerial-count.jpg';
    }
    if (product.sectors.contains('environment')) {
      return 'assets/images/store/environmental-monitoring.jpg';
    }
    return switch (product.category) {
      'seeds' => 'assets/images/store/certified-maize-seeds.jpg',
      'inputs' => 'assets/images/store/fertilizer-inputs.jpg',
      'equipment' => 'assets/images/store/rtk-field-system.jpg',
      'hardware' => 'assets/images/store/soil-iot-kit.jpg',
      'subscription' => 'assets/images/store/geovision-intelligence-pro.jpg',
      _ => 'assets/images/store/multispectral-drone-service.jpg',
    };
  }

  @override
  Widget build(BuildContext context) {
    final image = product.image?.trim();
    return ClipRRect(
      borderRadius: borderRadius,
      child: switch (image) {
        final path when path != null && path.startsWith('assets/') =>
          Image.asset(
            path,
            fit: fit,
            width: double.infinity,
            height: double.infinity,
            errorBuilder: (_, __, ___) => _assetFallback(),
          ),
        final url
            when url != null &&
                (url.startsWith('https://') || url.startsWith('http://')) =>
          Image.network(
            url,
            fit: fit,
            width: double.infinity,
            height: double.infinity,
            errorBuilder: (_, __, ___) => _assetFallback(),
          ),
        // Legacy backend paths such as /assets/img/products/foo.jpg are not
        // bundled mobile assets and are not absolute public URLs. Use the
        // deterministic product/sector photograph instead of a broken icon.
        _ => _assetFallback(),
      },
    );
  }

  Widget _assetFallback() => Image.asset(
        _fallbackAsset,
        fit: fit,
        width: double.infinity,
        height: double.infinity,
        errorBuilder: (_, __, ___) => _fallback(),
      );

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
