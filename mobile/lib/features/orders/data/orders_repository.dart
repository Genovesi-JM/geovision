import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/demo/demo_data.dart';
import '../../../core/networking/api_client.dart';
import '../../../integrations/payments/payment_provider.dart';
import '../domain/commerce.dart';
import '../domain/product.dart';

class OrdersRepository {
  OrdersRepository({
    required ApiClient api,
    required AppConfig config,
    required PaymentProvider payments,
    required SharedPreferences preferences,
  })  : _api = api,
        _config = config,
        _payments = payments,
        _preferences = preferences;

  final ApiClient _api;
  final AppConfig _config;
  final PaymentProvider _payments;
  final SharedPreferences _preferences;
  final Map<String, String> _remoteItemIds = {};
  static const _cartKey = 'gv_shop_cart_id';

  bool get isDemo => _config.demoMode;
  String get paymentProviderId => _payments.id;

  String get cartId {
    final existing = _preferences.getString(_cartKey);
    if (existing != null && existing.isNotEmpty) return existing;
    final random = Random.secure().nextInt(0x7fffffff).toRadixString(36);
    final generated = 'mobile_${DateTime.now().microsecondsSinceEpoch}_$random';
    _preferences.setString(_cartKey, generated);
    return generated;
  }

  Future<List<GvProduct>> catalogue() async {
    if (isDemo) return DemoData.products();
    final response = await _api.raw.get('/shop/products');
    final rows = response.data as List? ?? const [];
    return rows
        .whereType<Map>()
        .map((row) => GvProduct.fromJson(Map<String, dynamic>.from(row)))
        .toList();
  }

  Future<List<GvOrder>> orders() async {
    if (isDemo) return DemoData.orders();
    final response = await _api.raw.get('/shop/orders');
    final rows = response.data as List? ?? const [];
    return rows.whereType<Map>().map((raw) {
      final row = Map<String, dynamic>.from(raw);
      final count = (row['item_count'] as num?)?.toInt() ?? 0;
      return GvOrder(
        id: (row['id'] ?? row['order_number']).toString(),
        createdAt: DateTime.tryParse('${row['created_at'] ?? ''}') ??
            DateTime.fromMillisecondsSinceEpoch(0),
        totalCents: (row['total'] as num?)?.toInt() ?? 0,
        currency: (row['currency'] ?? 'AOA').toString(),
        status: (row['status'] ?? 'created').toString(),
        paymentStatus: _paymentStatus('${row['status'] ?? ''}'),
        items: ['$count ${count == 1 ? 'item' : 'items'}'],
      );
    }).toList();
  }

  Future<RemoteCart?> loadCart() async {
    if (isDemo) return null;
    final response = await _api.raw.get('/shop/cart/$cartId');
    return _remember(
        RemoteCart.fromJson(Map<String, dynamic>.from(response.data as Map)));
  }

  Future<RemoteCart?> addToCart(
      GvProduct product, int quantity, String currency) async {
    if (isDemo) return null;
    final response = await _api.raw.post('/shop/cart/$cartId/items', data: {
      'product_id': product.id,
      'quantity': quantity,
      'currency': currency,
    });
    return _remember(
        RemoteCart.fromJson(Map<String, dynamic>.from(response.data as Map)));
  }

  Future<RemoteCart?> updateQuantity(String productId, int quantity) async {
    if (isDemo) return null;
    var itemId = _remoteItemIds[productId];
    if (itemId == null) {
      await loadCart();
      itemId = _remoteItemIds[productId];
    }
    if (itemId == null) throw StateError('Cart item is not synchronized.');
    final response = quantity <= 0
        ? await _api.raw.delete('/shop/cart/$cartId/items/$itemId')
        : await _api.raw.put('/shop/cart/$cartId/items/$itemId',
            data: {'quantity': quantity});
    return _remember(
        RemoteCart.fromJson(Map<String, dynamic>.from(response.data as Map)));
  }

  Future<RemoteCart?> updateCurrency(String currency) async {
    if (isDemo) return null;
    final response = await _api.raw
        .patch('/shop/cart/$cartId/currency', data: {'currency': currency});
    return _remember(
        RemoteCart.fromJson(Map<String, dynamic>.from(response.data as Map)));
  }

  Future<CheckoutResult> checkout({
    required String currency,
    required String paymentMethod,
    required String name,
    required String email,
    String? phone,
    String? company,
    String? address,
    String? notes,
  }) async {
    if (isDemo) {
      return const CheckoutResult(
          success: true, orderNumber: 'DEMO-ORDER', paymentRequired: false);
    }
    final response = await _api.raw.post('/shop/checkout/$cartId', data: {
      'currency': currency,
      'payment_method': paymentMethod,
      'billing_info': {
        'name': name,
        'email': email,
        'phone': phone,
        'company_name': company,
        'address': address,
        'country': 'AO',
      },
      'customer_notes': notes,
    });
    final result = CheckoutResult.fromJson(
        Map<String, dynamic>.from(response.data as Map));
    if (result.success) {
      _remoteItemIds.clear();
      await _preferences.remove(_cartKey);
    }
    return result;
  }

  Future<PaymentResult> pay({required GvOrder order}) => _payments.createIntent(
      amountCents: order.totalCents,
      currency: order.currency,
      orderId: order.id);

  RemoteCart _remember(RemoteCart cart) {
    _remoteItemIds
      ..clear()
      ..addEntries(cart.items.map((item) => MapEntry(item.productId, item.id)));
    return cart;
  }

  String _paymentStatus(String status) => switch (status) {
        'paid' ||
        'processing' ||
        'dispatched' ||
        'delivered' ||
        'completed' =>
          'paid',
        'refunded' || 'partially_refunded' => 'refunded',
        _ => 'pending',
      };
}

final ordersRepositoryProvider = Provider<OrdersRepository>(
  (ref) => OrdersRepository(
    api: ref.watch(apiClientProvider),
    config: ref.watch(appConfigProvider),
    payments: ref.watch(paymentProviderProvider),
    preferences: ref.watch(sharedPrefsProvider),
  ),
);
final catalogueProvider = FutureProvider<List<GvProduct>>(
    (ref) => ref.watch(ordersRepositoryProvider).catalogue());
final ordersProvider = FutureProvider<List<GvOrder>>(
    (ref) => ref.watch(ordersRepositoryProvider).orders());
