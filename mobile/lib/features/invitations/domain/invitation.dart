class InvitationPreview {
  const InvitationPreview({
    required this.organizationName,
    required this.workspaceName,
    required this.emailHint,
    required this.role,
    required this.targetKind,
  });

  final String organizationName;
  final String workspaceName;
  final String emailHint;
  final String role;
  final String targetKind;

  factory InvitationPreview.fromJson(Map<String, dynamic> json) {
    final destination =
        Map<String, dynamic>.from(json['destination'] as Map? ?? const {});
    return InvitationPreview(
      organizationName: json['organization_name'] as String? ?? '',
      workspaceName: json['workspace_name'] as String? ?? '',
      emailHint: json['target_email_hint'] as String? ?? '',
      role: json['intended_role'] as String? ?? 'member',
      targetKind: destination['kind'] as String? ?? 'workspace',
    );
  }
}

class InvitationDestination {
  const InvitationDestination({
    required this.kind,
    required this.organizationId,
    required this.workspaceId,
    required this.path,
    this.targetId,
  });

  final String kind;
  final String organizationId;
  final String workspaceId;
  final String path;
  final String? targetId;

  factory InvitationDestination.fromJson(Map<String, dynamic> json) =>
      InvitationDestination(
        kind: json['kind'] as String? ?? 'workspace',
        organizationId: json['organization_id'] as String? ?? '',
        workspaceId: json['workspace_id'] as String? ?? '',
        path: json['path'] as String? ?? '/portal',
        targetId: json['target_id'] as String?,
      );
}
