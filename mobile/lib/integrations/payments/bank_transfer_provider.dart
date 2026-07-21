import 'payment_provider.dart';

/// Manual bank-transfer / IBAN provider. Always available; produces
/// instructions and a pending state until finance confirms the transfer.
class BankTransferProvider implements PaymentProvider {
  const BankTransferProvider();
  @override
  String get id => 'bank_transfer';
  @override
  bool get requiresCredentials => false;
  @override
  Future<PaymentResult> createIntent(
      {required int amountCents,
      required String currency,
      required String orderId}) async {
    return PaymentResult(
        status: 'pending',
        reference: 'BT-$orderId',
        message: 'Awaiting bank transfer confirmation.');
  }
}
