import 'package:flutter/material.dart';
import '../theme/app_colors.dart';

class GvSectionHeader extends StatelessWidget {
  const GvSectionHeader({super.key, required this.title, this.action});
  final String title;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            title,
            style: const TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: GvColors.textPrimary,
              letterSpacing: 0.2,
            ),
          ),
          if (action != null) action!,
        ],
      ),
    );
  }
}
