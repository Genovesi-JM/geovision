class RegistrationRequest {
  const RegistrationRequest({
    required this.email,
    required this.password,
    required this.fullName,
    this.intent,
    this.customerType = 'business',
    this.sectors = const [],
    this.useCases = const [],
    this.organisation,
  });

  final String email;
  final String password;
  final String fullName;
  final String? intent;
  final String customerType;
  final List<String> sectors;
  final List<String> useCases;
  final String? organisation;

  Map<String, dynamic> toJson() => {
        'email': email.trim().toLowerCase(),
        'password': password,
        'full_name': fullName.trim(),
        if (intent?.trim().isNotEmpty == true) 'intent': intent!.trim(),
        'customer_type': customerType,
        'sectors': sectors,
        'sector_focus': sectors.join(','),
        'use_cases': useCases,
        if (organisation?.trim().isNotEmpty == true)
          'org_name': organisation!.trim(),
      };
}
