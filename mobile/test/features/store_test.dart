import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/demo/demo_data.dart';
import 'package:geovision/features/orders/presentation/cart_controller.dart';
import 'package:geovision/features/orders/domain/currency.dart';
import 'package:geovision/features/orders/domain/commerce.dart';
import 'package:geovision/features/orders/domain/product.dart';
import 'package:geovision/features/orders/presentation/product_image.dart';
import 'package:geovision/features/orders/presentation/store_copy.dart';
import 'package:geovision/features/sites/domain/sector.dart';

void main() {
  testWidgets('store filters use the agreed Portuguese sector labels',
      (tester) async {
    late List<String> labels;
    late String legacyLabel;
    await tester.pumpWidget(Localizations(
      locale: const Locale('pt'),
      delegates: const [DefaultWidgetsLocalizations.delegate],
      child: Builder(builder: (context) {
        final copy = StoreCopy.of(context);
        labels = PublicSectorIds.values.map(copy.sector).toList();
        legacyLabel = copy.sector('PORTS_INDUSTRIAL');
        return const SizedBox.shrink();
      }),
    ));

    expect(labels, const [
      'Agricultura & Pecuária',
      'Construção & Infraestruturas',
      'Ambiente',
      'Mineração',
      'Indústria, Energia & Utilities',
      'Portos & Logística',
    ]);
    expect(legacyLabel, 'Portos & Logística');
  });

  test('demo catalogue contains only the current public product categories',
      () {
    final categories = DemoData.products().map((p) => p.category).toSet();
    expect(categories, {'hardware', 'service', 'subscription'});
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
    expect(delivery.destination, contains('Madrid'));
  });

  test('store presents deterministic AKZ, EUR and USD prices', () {
    expect(StoreCurrency.values.first, StoreCurrency.eur);
    const usdCents = 10000;
    expect(
        StoreMoney.formatUsdCents(usdCents, StoreCurrency.usd), contains(r'$'));
    expect(
        StoreMoney.formatUsdCents(usdCents, StoreCurrency.eur), contains('€'));
    expect(
        StoreMoney.formatUsdCents(usdCents, StoreCurrency.akz), contains('Kz'));
    expect(StoreMoney.allPrices(usdCents), hasLength(3));
  });

  test('catalogue matches current GeoVision sectors and declares deliverables',
      () {
    final products = DemoData.products();
    final sectors = products.expand((product) => product.sectors).toSet();
    expect(sectors, {
      'agriculture',
      'construction_infrastructure',
      'environment',
      'mining',
      'industry_energy_utilities',
      'ports_logistics',
    });
    expect(
        products.every((product) => product.description.length > 45), isTrue);
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
    expect(
        illustrated.any((product) => product.category == 'hardware'), isTrue);
    expect(illustrated.any((product) => product.category == 'service'), isTrue);
  });

  test('demo products are production IDs and include all mobile translations',
      () {
    const activeIds = {
      'prod_infra_progress_survey',
      'prod_infra_technical_inspection',
      'prod_infra_thermal_inspection',
      'prod_infra_3d_mapping',
      'prod_infra_specialist_review',
      'prod_infra_monitoring_plan',
      'prod_env_environmental_survey',
      'prod_env_reforestation_monitoring',
      'prod_env_targeted_drone_verification',
      'prod_env_sensor_installation',
      'prod_env_monitoring_plan',
      'prod_env_specialist_review',
      'prod_mining_volumetry_survey',
      'prod_mining_site_progress_survey',
      'prod_mining_lidar_specialist_survey',
      'prod_mining_environmental_monitoring',
      'prod_mining_repeat_monitoring_plan',
      'prod_ports_visual_inspection',
      'prod_ports_thermal_inspection',
      'prod_ports_3d_mapping',
      'prod_ports_sensor_installation',
      'prod_ports_monitoring_plan',
      'prod_ports_specialist_review',
      'prod_aerial_basic_mapping',
      'prod_agro_visual_inspection',
      'prod_supply_soil_probe',
      'prod_supply_irrigation_parts',
      'prod_kit_water_tank_starter',
      'prod_kit_environment_air',
    };
    final products = DemoData.products();
    expect(products.map((product) => product.id).toSet(), activeIds);
    for (final product in products) {
      expect(product.localizedName('en'), isNotEmpty);
      expect(product.localizedName('es'), isNotEmpty);
      expect(product.localizedName('fr'), isNotEmpty);
      expect(product.localizedDescription('en'), isNotEmpty);
    }
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
      'translations': {
        'en': {'name': 'NDVI Analysis', 'description': 'Multispectral mapping'}
      },
    });
    expect(product.category, 'service');
    expect(product.priceAkzCents, 45000000);
    expect(product.priceCents, 54500);
    expect(product.priceEurCents, 50000);
    expect(product.deliverables, ['Mapa NDVI']);
    expect(product.sectors, ['agriculture']);
    expect(product.featured, isTrue);
    expect(product.localizedName('en'), 'NDVI Analysis');
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
