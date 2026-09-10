import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/providers.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';

class CustomerSettingsScreen extends ConsumerWidget {
  const CustomerSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final locale = ref.watch(localeProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          GvCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(
                    Icons.notifications_outlined,
                    color: GvColors.accentCyan,
                  ),
                  title: const Text('Notification preferences'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => context.push('/notification-preferences'),
                ),
                ListTile(
                  leading: const Icon(
                    Icons.language,
                    color: GvColors.accentCyan,
                  ),
                  title: const Text('Language'),
                  subtitle: Text(locale.languageCode.toUpperCase()),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _selectLanguage(context, ref),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _selectLanguage(BuildContext context, WidgetRef ref) async {
    const languages = {
      'pt': 'Português',
      'en': 'English',
      'es': 'Español',
      'fr': 'Français',
    };
    final selected = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Language',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
            ),
            for (final language in languages.entries)
              ListTile(
                title: Text(language.value),
                trailing: ref.read(localeProvider).languageCode == language.key
                    ? const Icon(
                        Icons.check_circle,
                        color: GvColors.accentGreen,
                      )
                    : null,
                onTap: () => Navigator.pop(sheetContext, language.key),
              ),
          ],
        ),
      ),
    );
    if (selected != null) {
      await ref.read(localeProvider.notifier).select(Locale(selected));
    }
  }
}
