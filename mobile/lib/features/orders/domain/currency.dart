import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import 'product.dart';

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
    return formatCents(cents, target);
  }

  static String formatCents(int cents, StoreCurrency target) {
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

  static int productCents(GvProduct product, StoreCurrency target) =>
      switch (target) {
        StoreCurrency.usd => product.priceCents,
        StoreCurrency.eur =>
          product.priceEurCents ?? convertUsdCents(product.priceCents, target),
        StoreCurrency.akz =>
          product.priceAkzCents ?? convertUsdCents(product.priceCents, target),
      };

  static String formatProduct(GvProduct product, StoreCurrency target) {
    final cents = productCents(product, target);
    return formatCents(cents, target);
  }

  static List<String> allProductPrices(GvProduct product) =>
      StoreCurrency.values
          .map((currency) => formatProduct(product, currency))
          .toList();
}

final storeCurrencyProvider =
    StateProvider<StoreCurrency>((ref) => StoreCurrency.akz);
