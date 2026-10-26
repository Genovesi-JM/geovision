import 'package:flutter/widgets.dart';

/// Customer journey copy in the three primary product languages.
String journeyText(BuildContext context, String es, String en,
        {required String pt}) =>
    switch (Localizations.localeOf(context).languageCode) {
      'pt' => pt,
      'es' => es,
      _ => en,
    };
