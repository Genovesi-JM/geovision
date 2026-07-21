import 'payment_provider.dart';

/// PLACEHOLDER. Interface prepared; real Stripe SDK wiring is gated on
/// publishable/secret keys and App Store / Play billing review (HUMAN_GATES).
class StripePaymentProvider implements PaymentProvider {
  const StripePaymentProvider(this.publishableKey);
  final String publishableKey;
  @override
  String get id => 'stripe';
  @override
  bool get requiresCredentials => true;
  @override
  Future<PaymentResult> createIntent(
      {required int amountCents,
      required String currency,
      required String orderId}) async {
    throw UnimplementedError(
        'Stripe requires credentials — see HUMAN_GATES.md');
  }
}
