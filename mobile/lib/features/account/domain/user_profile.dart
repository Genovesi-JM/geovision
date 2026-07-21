class UserProfile {
  const UserProfile({
    required this.id,
    required this.email,
    this.fullName,
    this.organisation,
    this.role = 'customer',
    this.phone,
  });
  final String id;
  final String email;
  final String? fullName;
  final String? organisation;
  final String role;
  final String? phone;

  String get displayName => fullName?.isNotEmpty == true ? fullName! : email;

  factory UserProfile.fromJson(Map<String, dynamic> j) {
    final user = (j['user'] as Map?)?.cast<String, dynamic>() ?? j;
    final profile = (j['profile'] as Map?)?.cast<String, dynamic>();
    return UserProfile(
      id: (user['id'] ?? '').toString(),
      email: (user['email'] ?? '').toString(),
      fullName: (profile?['full_name'] ?? user['full_name'] ?? user['name'])
          as String?,
      organisation: profile?['company'] as String?,
      role: (user['role'] ?? 'customer').toString(),
      phone: profile?['phone'] as String?,
    );
  }
}
