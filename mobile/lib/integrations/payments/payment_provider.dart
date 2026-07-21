/// Result of a payment intent creation / confirmation.
class PaymentResult {
  const PaymentResult(
      {required this.status, required this.reference, this.message});
  final String status; // requires_action|pending|succeeded|failed
  final String reference;
  final String? message;
}

/// Abstract payment contract. Concrete providers: mock, Stripe, Multicaixa,
/// bank transfer. Production providers are feature-flagged and never activated
/// automatically (see HUMAN_GATES.md).
abstract interface class PaymentProvider {
  String get id;
  bool get requiresCredentials;
  Future<PaymentResult> createIntent(
      {required int amountCents,
      required String currency,
      required String orderId});
}
