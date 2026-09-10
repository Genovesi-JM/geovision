import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/notifications_repository.dart';
import '../domain/notification.dart';

class NotificationPreferencesScreen extends ConsumerWidget {
  const NotificationPreferencesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final preferences = ref.watch(notificationPreferencesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Notification settings')),
      body: preferences.when(
        loading: () => const GvLoading(label: 'Loading settings…'),
        error: (error, _) => GvErrorState(
          message: '$error',
          onRetry: () =>
              ref.read(notificationPreferencesProvider.notifier).load(),
        ),
        data: (items) => ListView(
          padding: const EdgeInsets.all(GvSpacing.lg),
          children: [
            const Text(
              'Choose how GeoVision contacts you for each kind of update. '
              'Critical events still remain in your notification history.',
              style: TextStyle(color: GvColors.textSecondary, fontSize: 13),
            ),
            const SizedBox(height: GvSpacing.lg),
            for (final preference in items) ...[
              _PreferenceCard(
                key: ValueKey(preference.category),
                preference: preference,
              ),
              const SizedBox(height: GvSpacing.sm),
            ],
          ],
        ),
      ),
    );
  }
}

class _PreferenceCard extends ConsumerStatefulWidget {
  const _PreferenceCard({super.key, required this.preference});

  final NotificationPreference preference;

  @override
  ConsumerState<_PreferenceCard> createState() => _PreferenceCardState();
}

class _PreferenceCardState extends ConsumerState<_PreferenceCard> {
  bool _saving = false;

  NotificationPreference get preference => widget.preference;

  @override
  Widget build(BuildContext context) {
    return GvCard(
      padding: EdgeInsets.zero,
      child: ExpansionTile(
        leading: Icon(_icon(preference.category), color: GvColors.accentCyan),
        title: Text(
          _label(preference.category),
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          _summary(preference),
          style: const TextStyle(color: GvColors.textMuted, fontSize: 11),
        ),
        trailing: _saving
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : null,
        children: [
          const Divider(height: 1),
          SwitchListTile.adaptive(
            title: const Text('In-app inbox'),
            secondary: const Icon(Icons.inbox_outlined),
            value: preference.inAppEnabled,
            onChanged: _saving
                ? null
                : (value) => _save(preference.copyWith(inAppEnabled: value)),
          ),
          SwitchListTile.adaptive(
            title: const Text('Push notifications'),
            secondary: const Icon(Icons.phone_iphone),
            value: preference.pushEnabled,
            onChanged: _saving
                ? null
                : (value) => _save(preference.copyWith(pushEnabled: value)),
          ),
          SwitchListTile.adaptive(
            title: const Text('Email'),
            secondary: const Icon(Icons.email_outlined),
            value: preference.emailEnabled,
            onChanged: _saving
                ? null
                : (value) => _save(preference.copyWith(emailEnabled: value)),
          ),
          SwitchListTile.adaptive(
            title: const Text('SMS'),
            subtitle:
                const Text('Used only when an SMS provider is available.'),
            secondary: const Icon(Icons.sms_outlined),
            value: preference.smsEnabled,
            onChanged: _saving
                ? null
                : (value) => _save(preference.copyWith(smsEnabled: value)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(
                GvSpacing.md, 0, GvSpacing.md, GvSpacing.md),
            child: DropdownButtonFormField<String>(
              key: ValueKey(preference.minimumSeverity),
              initialValue: preference.minimumSeverity,
              decoration: const InputDecoration(
                labelText: 'Minimum severity',
                prefixIcon: Icon(Icons.priority_high),
              ),
              items: const [
                DropdownMenuItem(value: 'INFO', child: Text('All updates')),
                DropdownMenuItem(
                    value: 'WATCH', child: Text('Watch or higher')),
                DropdownMenuItem(
                    value: 'WARNING', child: Text('Warnings or critical')),
                DropdownMenuItem(
                    value: 'CRITICAL', child: Text('Critical only')),
              ],
              onChanged: _saving
                  ? null
                  : (value) {
                      if (value != null) {
                        _save(preference.copyWith(minimumSeverity: value));
                      }
                    },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _save(NotificationPreference updated) async {
    setState(() => _saving = true);
    final failure =
        await ref.read(notificationPreferencesProvider.notifier).save(updated);
    if (!mounted) return;
    setState(() => _saving = false);
    if (failure != null) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(failure.message)));
    }
  }

  static String _summary(NotificationPreference preference) {
    final channels = <String>[
      if (preference.inAppEnabled) 'in-app',
      if (preference.pushEnabled) 'push',
      if (preference.emailEnabled) 'email',
      if (preference.smsEnabled) 'SMS',
    ];
    return channels.isEmpty ? 'History only' : channels.join(' · ');
  }

  static String _label(String category) => switch (category) {
        'INVITATION' => 'Invitations',
        'REPORT' => 'Reports',
        'ACTION' => 'Recommended actions',
        'DEVICE' => 'Devices and assets',
        'SERVICE' => 'Services',
        'ORDER' => 'Orders',
        'SHIPMENT' => 'Shipments',
        _ => 'System',
      };

  static IconData _icon(String category) => switch (category) {
        'INVITATION' => Icons.group_add_outlined,
        'REPORT' => Icons.description_outlined,
        'ACTION' => Icons.task_alt,
        'DEVICE' => Icons.sensors,
        'SERVICE' => Icons.home_repair_service_outlined,
        'ORDER' => Icons.shopping_bag_outlined,
        'SHIPMENT' => Icons.local_shipping_outlined,
        _ => Icons.info_outline,
      };
}
