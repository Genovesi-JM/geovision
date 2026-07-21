import 'payment_provider.dart';

class MockPaymentProvider implements PaymentProvider {
  const MockPaymentProvider();
  @override
  String get id => 'mock';
  @override
  bool get requiresCredentials => false;
  @override
  Future<PaymentResult> createIntent(
      {required int amountCents,
      required String currency,
      required String orderId}) async {
    await Future<void>.delayed(const Duration(milliseconds: 600));
    return PaymentResult(
        status: 'succeeded',
        reference: 'MOCK-$orderId',
        message: 'Demo payment approved.');
  }
}
