import 'package:flutter/material.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

/// Consistent loading / empty / error states used across every feature.
class GvLoading extends StatelessWidget {
  const GvLoading({super.key, this.label});
  final String? label;
  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(color: GvColors.accentCyan),
            if (label != null) ...[
              const SizedBox(height: GvSpacing.md),
              Text(label!,
                  style: const TextStyle(color: GvColors.textSecondary)),
            ],
          ],
        ),
      );
}

class GvEmpty extends StatelessWidget {
  const GvEmpty(
      {super.key, required this.message, this.icon = Icons.inbox_outlined});
  final String message;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(GvSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 48, color: GvColors.textMuted),
              const SizedBox(height: GvSpacing.md),
              Text(message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: GvColors.textSecondary)),
            ],
          ),
        ),
      );
}

class GvErrorState extends StatelessWidget {
  const GvErrorState({super.key, required this.message, this.onRetry});
  final String message;
  final VoidCallback? onRetry;
  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(GvSpacing.xl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: GvColors.high),
              const SizedBox(height: GvSpacing.md),
              Text(message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: GvColors.textSecondary)),
              if (onRetry != null) ...[
                const SizedBox(height: GvSpacing.lg),
                FilledButton(onPressed: onRetry, child: const Text('Retry')),
              ],
            ],
          ),
        ),
      );
}
