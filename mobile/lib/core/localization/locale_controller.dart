import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LocaleController extends StateNotifier<Locale> {
  LocaleController(this._preferences)
      : super(Locale(_preferences.getString(_key) ?? 'pt'));

  static const _key = 'gv_preferred_language';
  final SharedPreferences _preferences;

  Future<void> select(Locale locale) async {
    if (!const ['pt', 'en', 'es', 'fr'].contains(locale.languageCode)) return;
    state = Locale(locale.languageCode);
    await _preferences.setString(_key, locale.languageCode);
  }
}
