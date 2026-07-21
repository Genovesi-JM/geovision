class GvProduct {
  const GvProduct({
    required this.id,
    required this.name,
    required this.category,
    required this.priceCents,
    required this.currency,
    this.description = '',
    this.unit,
    this.stockStatus = 'in_stock',
    this.featured = false,
  });
  final String id;
  final String name;
  final String category; // service|hardware|subscription|input|report
  final int priceCents;
  final String currency;
  final String description;
  final String? unit;
  final String stockStatus;
  final bool featured;

  String get priceLabel => '${(priceCents / 100).toStringAsFixed(2)} $currency';

  factory GvProduct.fromJson(Map<String, dynamic> j) => GvProduct(
        id: j['id'].toString(),
        name: (j['name'] ?? '').toString(),
        category: (j['category'] ?? 'service').toString(),
        priceCents: (j['price_cents'] as num?)?.toInt() ?? 0,
        currency: (j['currency'] ?? 'USD').toString(),
        description: (j['description'] ?? '').toString(),
        unit: j['unit'] as String?,
        stockStatus: (j['stock_status'] ?? 'in_stock').toString(),
        featured: j['featured'] == true,
      );
}

class CartLine {
  const CartLine({required this.product, required this.quantity});
  final GvProduct product;
  final int quantity;
  int get totalCents => product.priceCents * quantity;
}

class GvOrder {
  const GvOrder({
    required this.id,
    required this.createdAt,
    required this.totalCents,
    required this.currency,
    required this.status,
    required this.paymentStatus,
    required this.items,
    this.delivery,
  });
  final String id;
  final DateTime createdAt;
  final int totalCents;
  final String currency;
  final String status; // quote|confirmed|fulfilled|cancelled
  final String paymentStatus; // unpaid|pending|paid|refunded
  final List<String> items;
  final GvDelivery? delivery;

  String get totalLabel => '${(totalCents / 100).toStringAsFixed(2)} $currency';
}

class GvDelivery {
  const GvDelivery({
    required this.trackingCode,
    required this.status,
    required this.destination,
    required this.estimatedArrival,
    required this.progress,
    required this.vehicleLatitude,
    required this.vehicleLongitude,
  });
  final String trackingCode;
  final String status;
  final String destination;
  final DateTime estimatedArrival;
  final double progress;
  final double vehicleLatitude;
  final double vehicleLongitude;
}
