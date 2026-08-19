import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/features/account/domain/account_profile.dart';
import 'package:geovision/features/account/domain/user_profile.dart';
import 'package:geovision/features/authentication/domain/registration_request.dart';

void main() {
  test('mobile onboarding exposes the same six public account types', () {
    expect(AccountProfiles.public.map((profile) => profile.id).toSet(), {
      'farm',
      'construction',
      'environment',
      'industry',
      'device',
      'enterprise',
    });
    for (final profile in AccountProfiles.public) {
      expect(profile.allowedSectors, contains(profile.defaultSector));
      expect(profile.allowedUseCases, containsAll(profile.defaultUseCases));
    }
  });

  test('registration request sends durable profile choices', () {
    const request = RegistrationRequest(
      email: ' User@Example.com ',
      password: 'strong-password',
      fullName: 'Geo User',
      customerType: 'construction',
      sectors: ['construction', 'environment'],
      useCases: ['progress', 'inspections'],
      organisation: 'Build Co',
    );
    expect(request.toJson(), containsPair('email', 'user@example.com'));
    expect(request.toJson(), containsPair('customer_type', 'construction'));
    expect(request.toJson(),
        containsPair('sector_focus', 'construction,environment'));
  });

  test('auth profile keeps account type, sectors and goals from API response',
      () {
    final profile = UserProfile.fromJson({
      'user': {'id': 'u1', 'email': 'user@example.com', 'role': 'cliente'},
      'account': {
        'id': 'a1',
        'name': 'Build Co',
        'customer_type': 'construction',
        'dashboard_profile': 'construction',
        'sector_focus': 'construction,environment',
        'use_cases': ['progress', 'inspections'],
      },
    });
    expect(profile.accountId, 'a1');
    expect(profile.organisation, 'Build Co');
    expect(profile.customerType, 'construction');
    expect(profile.dashboardProfile, 'construction');
    expect(profile.sectors, ['construction', 'environment']);
    expect(profile.useCases, ['progress', 'inspections']);
  });
}
