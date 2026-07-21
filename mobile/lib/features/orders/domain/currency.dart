import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

enum StoreCurrency { akz, eur, usd }

extension StoreCurrencyValue on StoreCurrency {
  String get code => switch (this) {
        StoreCurrency.akz => 'AKZ',
        StoreCurrency.eur => 'EUR',
        StoreCurrency.usd => 'USD',
      };

  String get symbol => switch (this) {
        StoreCurrency.akz => 'Kz',
        StoreCurrency.eur => '€',
        StoreCurrency.usd => r'$',
      };
}

/// Reference rates for demo presentation only. Production prices must come
/// from the commerce API as an explicit price list, never an unrecorded live
/// conversion during checkout.
abstract final class StoreMoney {
  static const double akzPerUsd = 900;
  static const double eurPerUsd = .92;

  static int convertUsdCents(int usdCents, StoreCurrency target) =>
      switch (target) {
        StoreCurrency.usd => usdCents,
        StoreCurrency.eur => (usdCents * eurPerUsd).round(),
        StoreCurrency.akz => (usdCents * akzPerUsd).round(),
      };

  static String formatUsdCents(int usdCents, StoreCurrency target) {
    final cents = convertUsdCents(usdCents, target);
    final locale = target == StoreCurrency.akz ? 'pt_AO' : 'en_US';
    return NumberFormat.currency(
      locale: locale,
      symbol: target.symbol,
      decimalDigits: target == StoreCurrency.akz ? 0 : 2,
    ).format(cents / 100);
  }

  static List<String> allPrices(int usdCents) => StoreCurrency.values
      .map((currency) => formatUsdCents(usdCents, currency))
      .toList();
}

final storeCurrencyProvider =
    StateProvider<StoreCurrency>((ref) => StoreCurrency.akz);
