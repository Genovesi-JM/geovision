import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/customer_experience_repository.dart';

class CustomerTeamMember {
  const CustomerTeamMember({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    required this.status,
  });

  final String id;
  final String name;
  final String email;
  final String role;
  final String status;

  factory CustomerTeamMember.fromJson(Map<String, dynamic> json) =>
      CustomerTeamMember(
        id: '${json['id'] ?? ''}',
        name: '${json['name'] ?? ''}',
        email: '${json['email'] ?? ''}',
        role: '${json['role'] ?? 'member'}',
        status: '${json['status'] ?? 'active'}',
      );
}

final customerTeamProvider =
    FutureProvider.autoDispose<List<CustomerTeamMember>>((ref) async {
  final experience = await ref.watch(customerExperienceProvider.future);
  final config = ref.watch(appConfigProvider);
  if (config.demoMode) {
    return const [
      CustomerTeamMember(
        id: 'demo-team-owner',
        name: 'GeoVision Customer',
        email: 'customer@example.com',
        role: 'owner',
        status: 'active',
      ),
      CustomerTeamMember(
        id: 'demo-team-member',
        name: 'Operations Manager',
        email: 'operations@example.com',
        role: 'manager',
        status: 'active',
      ),
    ];
  }
  final organizationId = experience.activeOrganizationId;
  if (organizationId == null || organizationId.isEmpty) return const [];
  final response = await ref
      .watch(apiClientProvider)
      .raw
      .get('/organizations/$organizationId/members');
  return (response.data as List? ?? const [])
      .whereType<Map>()
      .map((row) => CustomerTeamMember.fromJson(Map<String, dynamic>.from(row)))
      .where((member) => member.id.isNotEmpty)
      .toList();
});

class TeamScreen extends ConsumerWidget {
  const TeamScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final team = ref.watch(customerTeamProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Team')),
      body: team.when(
        loading: () => const GvLoading(label: 'Loading team…'),
        error: (_, __) => GvErrorState(
          message: 'The workspace team could not be loaded.',
          onRetry: () => ref.invalidate(customerTeamProvider),
        ),
        data: (members) => members.isEmpty
            ? const GvEmpty(
                message: 'No team members are available.',
                icon: Icons.group_outlined,
              )
            : ListView.separated(
                padding: const EdgeInsets.all(GvSpacing.lg),
                itemCount: members.length,
                separatorBuilder: (_, __) =>
                    const SizedBox(height: GvSpacing.sm),
                itemBuilder: (context, index) {
                  final member = members[index];
                  final displayName = member.name.isEmpty
                      ? (member.email.isEmpty ? 'Team member' : member.email)
                      : member.name;
                  return GvCard(
                    child: Row(
                      children: [
                        CircleAvatar(
                          backgroundColor:
                              GvColors.accentCyan.withValues(alpha: 0.16),
                          child: Text(
                            displayName.substring(0, 1).toUpperCase(),
                          ),
                        ),
                        const SizedBox(width: GvSpacing.md),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                displayName,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              if (member.name.isNotEmpty)
                                Text(
                                  member.email,
                                  style: const TextStyle(
                                    color: GvColors.textMuted,
                                    fontSize: 12,
                                  ),
                                ),
                            ],
                          ),
                        ),
                        Chip(label: Text(member.role)),
                      ],
                    ),
                  );
                },
              ),
      ),
    );
  }
}
