import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/features/guides/domain/help_guide.dart';

void main() {
  test('visual help covers devices, equipment, app, insights and safety', () {
    expect(helpGuides.length, greaterThanOrEqualTo(6));
    expect(helpGuides.map((guide) => guide.category).toSet(),
        containsAll(GuideCategory.values));
    for (final guide in helpGuides) {
      expect(guide.steps.length, greaterThanOrEqualTo(4));
      for (final language in ['pt', 'en', 'es', 'fr']) {
        expect(guideText(guide.title, language), isNotEmpty);
        expect(guideText(guide.summary, language), isNotEmpty);
        for (final step in guide.steps) {
          expect(guideText(step.title, language), isNotEmpty);
          expect(guideText(step.body, language), isNotEmpty);
        }
      }
    }
  });

  test('high-risk guides direct customers to qualified support', () {
    final protected = helpGuides.where((guide) => guide.requiresTechnician);
    expect(protected, isNotEmpty);
    expect(protected.every((guide) => guide.warning != null), isTrue);
  });
}
