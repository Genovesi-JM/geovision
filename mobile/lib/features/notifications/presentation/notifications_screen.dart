import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/notifications_repository.dart';
import '../domain/notification.dart';

class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() =>
      _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  bool _unreadOnly = false;
  final Set<String> _opening = {};

  @override
  Widget build(BuildContext context) {
    final inbox = ref.watch(notificationInboxProvider);
    final unread = inbox.valueOrNull?.unread ?? 0;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          if (unread > 0)
            IconButton(
              tooltip: 'Mark all as read',
              onPressed: _markAllRead,
              icon: const Icon(Icons.done_all),
            ),
          IconButton(
            tooltip: 'Notification settings',
            onPressed: () => context.go('/notification-preferences'),
            icon: const Icon(Icons.tune),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
                GvSpacing.lg, GvSpacing.sm, GvSpacing.lg, 0),
            child: Row(
              children: [
                _FilterChip(
                  label: 'All',
                  selected: !_unreadOnly,
                  onSelected: () => _setUnreadOnly(false),
                ),
                const SizedBox(width: GvSpacing.sm),
                _FilterChip(
                  label: unread > 0 ? 'Unread ($unread)' : 'Unread',
                  selected: _unreadOnly,
                  onSelected: () => _setUnreadOnly(true),
                ),
              ],
            ),
          ),
          Expanded(
            child: inbox.when(
              loading: () => const GvLoading(label: 'Loading notifications…'),
              error: (error, _) => GvErrorState(
                message: '$error',
                onRetry: () => ref
                    .read(notificationInboxProvider.notifier)
                    .load(unreadOnly: _unreadOnly),
              ),
              data: (page) => page.items.isEmpty
                  ? GvEmpty(
                      icon: _unreadOnly
                          ? Icons.mark_email_read_outlined
                          : Icons.notifications_none,
                      message: _unreadOnly
                          ? 'You have read every notification.'
                          : 'No notifications yet.',
                    )
                  : RefreshIndicator(
                      onRefresh: () => ref
                          .read(notificationInboxProvider.notifier)
                          .load(unreadOnly: _unreadOnly),
                      child: ListView.separated(
                        padding: const EdgeInsets.all(GvSpacing.lg),
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: page.items.length,
                        separatorBuilder: (_, __) =>
                            const SizedBox(height: GvSpacing.sm),
                        itemBuilder: (context, index) {
                          final item = page.items[index];
                          return _NotificationTile(
                            notification: item,
                            opening: _opening.contains(item.id),
                            onTap: () => _open(item),
                          );
                        },
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  void _setUnreadOnly(bool value) {
    if (_unreadOnly == value) return;
    setState(() => _unreadOnly = value);
    ref.read(notificationInboxProvider.notifier).load(unreadOnly: value);
  }

  Future<void> _markAllRead() async {
    final failure =
        await ref.read(notificationInboxProvider.notifier).markAllRead();
    if (failure != null && mounted) _showError(failure.message);
  }

  Future<void> _open(GvNotification notification) async {
    if (_opening.contains(notification.id)) return;
    setState(() => _opening.add(notification.id));
    final controller = ref.read(notificationInboxProvider.notifier);
    final readFailure =
        notification.isRead ? null : await controller.markRead(notification.id);

    if (notification.targetType == 'NONE' || notification.targetId == null) {
      if (mounted) {
        setState(() => _opening.remove(notification.id));
        if (readFailure != null) _showError(readFailure.message);
      }
      return;
    }

    final result = await ref
        .read(notificationsRepositoryProvider)
        .resolveTarget(notification.id);
    if (!mounted) return;
    setState(() => _opening.remove(notification.id));
    result.when(
      ok: (target) => context.go(target.appPath),
      err: (failure) => _showError(failure.message),
    );
    if (readFailure != null) _showError(readFailure.message);
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onSelected,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;

  @override
  Widget build(BuildContext context) => ChoiceChip(
        label: Text(label),
        selected: selected,
        onSelected: (_) => onSelected(),
      );
}

class _NotificationTile extends StatelessWidget {
  const _NotificationTile({
    required this.notification,
    required this.opening,
    required this.onTap,
  });

  final GvNotification notification;
  final bool opening;
  final VoidCallback onTap;

  Color get _severityColor => switch (notification.severity) {
        'CRITICAL' => GvColors.critical,
        'WARNING' => GvColors.high,
        'WATCH' => GvColors.medium,
        _ => GvColors.accentSky,
      };

  IconData get _icon => switch (notification.category) {
        'REPORT' => Icons.description_outlined,
        'ACTION' => Icons.task_alt,
        'DEVICE' => Icons.sensors,
        'SERVICE' => Icons.home_repair_service_outlined,
        'ORDER' => Icons.shopping_bag_outlined,
        'SHIPMENT' => Icons.local_shipping_outlined,
        'INVITATION' => Icons.group_add_outlined,
        _ => Icons.info_outline,
      };

  @override
  Widget build(BuildContext context) {
    final time = DateFormat.MMMd()
        .add_Hm()
        .format(notification.lastOccurredAt.toLocal());
    final repeat = notification.occurrenceCount > 1
        ? ' · ${notification.occurrenceCount} updates'
        : '';
    return Semantics(
      button: true,
      readOnly: notification.isRead,
      label:
          '${notification.isRead ? 'Read' : 'Unread'} ${notification.severity.toLowerCase()} notification. ${notification.title}',
      child: GvCard(
        onTap: opening ? null : onTap,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: _severityColor.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(GvSpacing.radiusSm),
              ),
              child: Icon(_icon, color: _severityColor, size: 21),
            ),
            const SizedBox(width: GvSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(
                        child: Text(
                          notification.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontWeight: notification.isRead
                                ? FontWeight.w600
                                : FontWeight.w800,
                          ),
                        ),
                      ),
                      if (!notification.isRead)
                        Container(
                          width: 8,
                          height: 8,
                          margin: const EdgeInsets.only(top: 5, left: 8),
                          decoration: const BoxDecoration(
                            color: GvColors.accentCyan,
                            shape: BoxShape.circle,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    notification.body,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: GvColors.textSecondary, fontSize: 13),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    '$time$repeat',
                    style: const TextStyle(
                        color: GvColors.textMuted, fontSize: 11),
                  ),
                ],
              ),
            ),
            const SizedBox(width: GvSpacing.xs),
            if (opening)
              const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            else if (notification.targetType != 'NONE')
              const Icon(Icons.chevron_right,
                  color: GvColors.textMuted, size: 20),
          ],
        ),
      ),
    );
  }
}
