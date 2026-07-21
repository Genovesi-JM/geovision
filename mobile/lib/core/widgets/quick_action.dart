import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

class QuickAction extends StatelessWidget {
  const QuickAction(
      {super.key,
      required this.icon,
      required this.label,
      required this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
            vertical: GvSpacing.md, horizontal: GvSpacing.sm),
        decoration: BoxDecoration(
          color: GvColors.surfaceDeep,
          borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
          border: Border.all(color: GvColors.border),
        ),
        child: Column(
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                gradient: GvColors.gradientAccent,
                borderRadius: BorderRadius.circular(GvSpacing.radiusSm),
              ),
              child: Icon(icon, color: GvColors.bgDarker, size: 20),
            ),
            const SizedBox(height: 6),
            Text(label,
                textAlign: TextAlign.center,
                maxLines: 2,
                style: const TextStyle(
                    color: GvColors.textSecondary, fontSize: 11)),
          ],
        ),
      ),
    );
  }
}
