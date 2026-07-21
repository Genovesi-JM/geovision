import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/demo/demo_data.dart';
import 'package:geovision/features/orders/presentation/cart_controller.dart';

void main() {
  test('commerce catalogue covers customer product categories', () {
    final categories = DemoData.products().map((p) => p.category).toSet();
    expect(categories,
        containsAll(['seeds', 'inputs', 'equipment', 'hardware', 'service']));
  });

  test('cart calculates quantities and removes empty lines', () {
    final controller = CartController();
    final product = DemoData.products().first;
    controller.add(product);
    controller.add(product);
    expect(controller.state.single.quantity, 2);
    expect(controller.state.single.totalCents, product.priceCents * 2);
    controller.changeQuantity(product.id, 0);
    expect(controller.state, isEmpty);
  });

  test('demo order exposes trackable delivery', () {
    final delivery =
        DemoData.orders().where((o) => o.delivery != null).single.delivery!;
    expect(delivery.trackingCode, isNotEmpty);
    expect(delivery.progress, inInclusiveRange(0, 1));
    expect(delivery.destination, contains('Luanda'));
  });
}
