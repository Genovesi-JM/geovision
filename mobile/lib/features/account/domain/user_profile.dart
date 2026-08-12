class UserProfile {
  const UserProfile({
    required this.id,
    required this.email,
    this.fullName,
    this.organisation,
    this.role = 'customer',
    this.phone,
    this.accountId,
    this.customerType = 'farm',
    this.dashboardProfile = 'farm',
    this.sectors = const [],
    this.useCases = const [],
  });
  final String id;
  final String email;
  final String? fullName;
  final String? organisation;
  final String role;
  final String? phone;
  final String? accountId;
  final String customerType;
  final String dashboardProfile;
  final List<String> sectors;
  final List<String> useCases;

  String get displayName => fullName?.isNotEmpty == true ? fullName! : email;

  factory UserProfile.fromJson(Map<String, dynamic> j) {
    final user = (j['user'] as Map?)?.cast<String, dynamic>() ?? j;
    final profile = (j['profile'] as Map?)?.cast<String, dynamic>();
    final accounts = j['accounts'] as List?;
    final account = (j['account'] as Map?)?.cast<String, dynamic>() ??
        (accounts?.isNotEmpty == true
            ? (accounts!.first as Map).cast<String, dynamic>()
            : <String, dynamic>{
                'id': j['account_id'],
                'name': j['account_name'],
                'customer_type': j['customer_type'],
                'dashboard_profile': j['dashboard_profile'],
                'sector_focus': j['sector_focus'],
                'use_cases': j['use_cases'],
              });

    List<String> stringList(dynamic value) {
      if (value is List) return value.map((item) => item.toString()).toList();
      if (value is String) {
        return value
            .split(',')
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList();
      }
      return const [];
    }

    return UserProfile(
      id: (user['id'] ?? '').toString(),
      email: (user['email'] ?? '').toString(),
      fullName: (profile?['full_name'] ?? user['full_name'] ?? user['name'])
          as String?,
      organisation: (profile?['company'] ??
              profile?['org_name'] ??
              account['org_name'] ??
              account['name'] ??
              j['company'] ??
              j['account_name'])
          ?.toString(),
      role: (user['role'] ?? 'customer').toString(),
      phone: profile?['phone'] as String?,
      accountId: (account['id'] ?? j['account_id'])?.toString(),
      customerType:
          (account['customer_type'] ?? j['customer_type'] ?? 'farm').toString(),
      dashboardProfile:
          (account['dashboard_profile'] ?? j['dashboard_profile'] ?? 'farm')
              .toString(),
      sectors: stringList(account['sectors'] ?? account['sector_focus']),
      useCases: stringList(account['use_cases']),
    );
  }
}
