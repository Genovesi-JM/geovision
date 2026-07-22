import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/demo/demo_data.dart';
import 'package:geovision/features/orders/presentation/cart_controller.dart';
import 'package:geovision/features/orders/domain/currency.dart';
import 'package:geovision/features/orders/domain/commerce.dart';
import 'package:geovision/features/orders/domain/product.dart';
import 'package:geovision/features/orders/presentation/product_image.dart';

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

  test('store presents deterministic AKZ, EUR and USD prices', () {
    const usdCents = 10000;
    expect(
        StoreMoney.formatUsdCents(usdCents, StoreCurrency.usd), contains(r'$'));
    expect(
        StoreMoney.formatUsdCents(usdCents, StoreCurrency.eur), contains('€'));
    expect(
        StoreMoney.formatUsdCents(usdCents, StoreCurrency.akz), contains('Kz'));
    expect(StoreMoney.allPrices(usdCents), hasLength(3));
  });

  test('catalogue matches GeoVision sectors and declares deliverables', () {
    final products = DemoData.products();
    final sectors = products.expand((product) => product.sectors).toSet();
    expect(
        sectors,
        containsAll([
          'agro',
          'livestock',
          'mining',
          'construction',
          'infrastructure',
          'environment'
        ]));
    expect(
        products.every((product) => product.description.length > 80), isTrue);
    expect(
        products.every((product) => product.deliverables.isNotEmpty), isTrue);
  });

  test('catalogue uses explicit backend-aligned currency price lists', () {
    final product = DemoData.products().first;
    expect(product.priceAkzCents, isNotNull);
    expect(product.priceEurCents, isNotNull);
    expect(
      StoreMoney.productCents(product, StoreCurrency.akz),
      product.priceAkzCents,
    );
  });

  test('commercial catalogue includes bundled product photography', () {
    final products = DemoData.products();
    final illustrated = products
        .where((product) =>
            product.image?.startsWith('assets/images/store/') == true)
        .toList();
    expect(illustrated.length, products.length,
        reason: 'Every commercial card must have a product image.');
    expect(illustrated.any((product) => product.category == 'seeds'), isTrue);
    expect(
        illustrated.any((product) => product.category == 'hardware'), isTrue);
    expect(
        illustrated.any((product) => product.category == 'equipment'), isTrue);
    expect(illustrated.any((product) => product.category == 'service'), isTrue);
  });

  test('maps the FastAPI product contract into mobile catalogue fields', () {
    final product = GvProduct.fromJson({
      'id': 'prod_agro_ndvi',
      'name': 'Análise NDVI',
      'description': 'Mapeamento multiespectral',
      'product_type': 'service',
      'category': 'flight',
      'price': 45000000,
      'price_usd': 54500,
      'price_eur': 50000,
      'currency': 'AOA',
      'unit_label': 'operação',
      'sectors': ['agro'],
      'deliverables': ['Mapa NDVI'],
      'is_featured': true,
    });
    expect(product.category, 'service');
    expect(product.priceAkzCents, 45000000);
    expect(product.priceCents, 54500);
    expect(product.priceEurCents, 50000);
    expect(product.deliverables, ['Mapa NDVI']);
    expect(product.featured, isTrue);
  });

  testWidgets('legacy backend image paths render a bundled photo fallback',
      (tester) async {
    final product = GvProduct.fromJson({
      'id': 'prod_agro_ndvi',
      'name': 'NDVI',
      'product_type': 'service',
      'image_url': '/assets/img/products/agro-ndvi.jpg',
      'sectors': ['agro'],
    });
    await tester.pumpWidget(MaterialApp(
      home: SizedBox(
          width: 180, height: 180, child: ProductImage(product: product)),
    ));
    final image = tester.widget<Image>(find.byType(Image));
    expect((image.image as AssetImage).assetName,
        'assets/images/store/multispectral-drone-service.jpg');
  });

  test('maps backend cart and checkout responses without losing totals', () {
    final cart = RemoteCart.fromJson({
      'id': 'cart-1',
      'currency': 'AOA',
      'item_count': 2,
      'subtotal': 90000000,
      'discount_amount': 0,
      'tax_amount': 11052632,
      'delivery_cost': 0,
      'total': 90000000,
      'items': [
        {
          'id': 'line-1',
          'product_id': 'prod-1',
          'quantity': 2,
          'unit_price': 45000000,
          'total_price': 90000000,
        }
      ],
    });
    expect(cart.total, 90000000);
    expect(cart.items.single.quantity, 2);
    final checkout = CheckoutResult.fromJson({
      'success': true,
      'order_id': 'order-1',
      'order_number': 'GV-2026-000001',
      'payment_required': true,
      'payment_method': 'iban_angola',
      'payment_data': {'reference': 'GV2026000001'},
    });
    expect(checkout.success, isTrue);
    expect(checkout.paymentData['reference'], 'GV2026000001');
  });
}
