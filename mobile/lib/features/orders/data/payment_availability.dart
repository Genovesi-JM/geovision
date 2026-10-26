import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../app/providers.dart';

const paymentLabels = {
  'visa_mastercard': 'Visa / Mastercard',
  'iban_international': 'SEPA / IBAN',
  'paypal': 'PayPal',
  'iban_angola': 'IBAN Angola',
  'multicaixa_express': 'Multicaixa Express',
};

final availablePaymentsProvider = FutureProvider<List<String>>((ref) async {
  final config = ref.watch(appConfigProvider);
  if (config.demoMode) return paymentLabels.keys.toList();
  // A disabled or mock mobile integration must never offer a real checkout.
  if (const ['disabled', 'mock', ''].contains(config.paymentProvider)) {
    return [];
  }
  final response =
      await ref.watch(apiClientProvider).raw.get('/shop/payment-methods');
  final methods = (response.data as Map)['methods'] as List? ?? [];
  // The mobile checkout currently supports manual bank instructions only.
  // Card/PayPal/Multicaixa need a complete native authorization/redirect flow.
  if (config.paymentProvider != 'bank_transfer') return [];
  return methods
      .whereType<Map>()
      .where((m) => m['enabled'] == true && m['settles'] == true)
      .map((m) => '${m['method']}')
      .where((m) => m == 'iban_international' || m == 'iban_angola')
      .toList();
});
