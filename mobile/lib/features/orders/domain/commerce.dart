class RemoteCart {
  const RemoteCart({
    required this.id,
    required this.currency,
    required this.itemCount,
    required this.subtotal,
    required this.discount,
    required this.tax,
    required this.delivery,
    required this.total,
    required this.items,
  });

  final String id;
  final String currency;
  final int itemCount;
  final int subtotal;
  final int discount;
  final int tax;
  final int delivery;
  final int total;
  final List<RemoteCartItem> items;

  factory RemoteCart.fromJson(Map<String, dynamic> json) => RemoteCart(
        id: json['id'].toString(),
        currency: (json['currency'] ?? 'AOA').toString(),
        itemCount: (json['item_count'] as num?)?.toInt() ?? 0,
        subtotal: (json['subtotal'] as num?)?.toInt() ?? 0,
        discount: (json['discount_amount'] as num?)?.toInt() ?? 0,
        tax: (json['tax_amount'] as num?)?.toInt() ?? 0,
        delivery: (json['delivery_cost'] as num?)?.toInt() ?? 0,
        total: (json['total'] as num?)?.toInt() ?? 0,
        items: (json['items'] as List? ?? const [])
            .whereType<Map>()
            .map((item) =>
                RemoteCartItem.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
      );
}

class RemoteCartItem {
  const RemoteCartItem(
      {required this.id,
      required this.productId,
      required this.quantity,
      required this.unitPrice,
      required this.total});
  final String id;
  final String productId;
  final int quantity;
  final int unitPrice;
  final int total;

  factory RemoteCartItem.fromJson(Map<String, dynamic> json) => RemoteCartItem(
        id: json['id'].toString(),
        productId: json['product_id'].toString(),
        quantity: (json['quantity'] as num?)?.toInt() ?? 0,
        unitPrice: (json['unit_price'] as num?)?.toInt() ?? 0,
        total: (json['total_price'] as num?)?.toInt() ?? 0,
      );
}

class CheckoutResult {
  const CheckoutResult({
    required this.success,
    this.orderId,
    this.orderNumber,
    this.paymentRequired = false,
    this.paymentMethod,
    this.paymentData = const {},
    this.error,
  });
  final bool success;
  final String? orderId;
  final String? orderNumber;
  final bool paymentRequired;
  final String? paymentMethod;
  final Map<String, dynamic> paymentData;
  final String? error;

  factory CheckoutResult.fromJson(Map<String, dynamic> json) => CheckoutResult(
        success: json['success'] == true,
        orderId: json['order_id']?.toString(),
        orderNumber: json['order_number']?.toString(),
        paymentRequired: json['payment_required'] == true,
        paymentMethod: json['payment_method']?.toString(),
        paymentData:
            Map<String, dynamic>.from(json['payment_data'] as Map? ?? const {}),
        error: json['error']?.toString(),
      );
}
