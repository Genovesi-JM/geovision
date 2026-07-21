import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/localization/locale_controller.dart';
import 'package:geovision/l10n/app_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  test('supports and persists Portuguese, English, Spanish and French',
      () async {
    expect(
      AppLocalizations.supportedLocales.map((locale) => locale.languageCode),
      containsAll(['pt', 'en', 'es', 'fr']),
    );
    SharedPreferences.setMockInitialValues({});
    final preferences = await SharedPreferences.getInstance();
    final controller = LocaleController(preferences);
    await controller.select(const Locale('es'));
    expect(controller.state.languageCode, 'es');
    expect(LocaleController(preferences).state.languageCode, 'es');
    await controller.select(const Locale('fr'));
    expect(LocaleController(preferences).state.languageCode, 'fr');
  });
}
