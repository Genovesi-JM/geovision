import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/features/account/domain/account_profile.dart';
import 'package:geovision/features/account/domain/user_profile.dart';
import 'package:geovision/features/authentication/domain/registration_request.dart';
import 'package:geovision/features/authentication/presentation/registration_copy.dart';
import 'package:geovision/features/sites/domain/sector.dart';

void main() {
  testWidgets('registration and account copy use the agreed Portuguese labels',
      (tester) async {
    late List<String> labels;
    late String legacyLabel;
    await tester.pumpWidget(Localizations(
      locale: const Locale('pt'),
      delegates: const [DefaultWidgetsLocalizations.delegate],
      child: Builder(builder: (context) {
        final copy = RegistrationCopy.of(context);
        labels = PublicSectorIds.values.map(copy.sector).toList();
        legacyLabel = copy.sector('agro');
        return const SizedBox.shrink();
      }),
    ));

    expect(labels, const [
      'Agricultura & Pecuária',
      'Construção & Infraestruturas',
      'Ambiente',
      'Mineração',
      'Indústria, Energia & Utilities',
      'Portos & Logística',
    ]);
    expect(legacyLabel, 'Agricultura & Pecuária');
  });

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
    expect(
      AccountProfiles.public
          .expand((profile) => profile.allowedSectors)
          .toSet(),
      containsAll(PublicSectorIds.values),
    );
    expect(AccountProfiles.byId('industry').allowedSectors, const [
      'industry_energy_utilities',
      'mining',
      'ports_logistics',
    ]);
  });

  test('registration request sends durable profile choices', () {
    const request = RegistrationRequest(
      email: ' User@Example.com ',
      password: 'strong-password',
      fullName: 'Geo User',
      customerType: 'construction',
      sectors: ['construction', 'environment', 'infrastructure'],
      useCases: ['progress', 'inspections'],
      organisation: 'Build Co',
    );
    expect(request.toJson(), containsPair('email', 'user@example.com'));
    expect(request.toJson(), containsPair('customer_type', 'construction'));
    expect(
        request.toJson(),
        containsPair(
            'sectors', ['construction_infrastructure', 'environment']));
    expect(
        request.toJson(),
        containsPair(
            'sector_focus', 'construction_infrastructure,environment'));
  });

  test('service-first registration sends intent without requiring a profile',
      () {
    const request = RegistrationRequest(
      email: 'invite@example.com',
      password: 'strong-password',
      fullName: 'Invite User',
      intent: 'view_invitation',
    );
    expect(request.toJson(), containsPair('intent', 'view_invitation'));
    expect(request.toJson()['sectors'], isEmpty);
    expect(request.toJson()['use_cases'], isEmpty);
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
    expect(profile.sectors, ['construction_infrastructure', 'environment']);
    expect(profile.useCases, ['progress', 'inspections']);
  });

  test('auth profile preserves the comma inside the known industry label', () {
    final profile = UserProfile.fromJson({
      'user': {'id': 'u2', 'email': 'industry@example.com'},
      'account': {
        'id': 'a2',
        'sector_focus': 'Agricultura & Pecuária,Indústria, Energia & Utilities,'
            'Portos & Logística,future_sector',
      },
    });

    expect(profile.sectors, const [
      PublicSectorIds.agriculture,
      PublicSectorIds.industryEnergyUtilities,
      PublicSectorIds.portsLogistics,
    ]);
  });
}
