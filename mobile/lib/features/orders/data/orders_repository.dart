import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/demo/demo_data.dart';
import '../../../integrations/payments/payment_provider.dart';
import '../domain/product.dart';

class OrdersRepository {
  OrdersRepository(this._payments);
  final PaymentProvider _payments;

  Future<List<GvProduct>> catalogue() async => DemoData.products();
  Future<List<GvOrder>> orders() async => DemoData.orders();

  Future<PaymentResult> pay({required GvOrder order}) => _payments.createIntent(
      amountCents: order.totalCents,
      currency: order.currency,
      orderId: order.id);

  String get paymentProviderId => _payments.id;
}

final ordersRepositoryProvider = Provider<OrdersRepository>(
  (ref) => OrdersRepository(ref.watch(paymentProviderProvider)),
);
final catalogueProvider = FutureProvider<List<GvProduct>>(
    (ref) => ref.watch(ordersRepositoryProvider).catalogue());
final ordersProvider = FutureProvider<List<GvOrder>>(
    (ref) => ref.watch(ordersRepositoryProvider).orders());
