class GvProduct {
  const GvProduct({
    required this.id,
    required this.name,
    required this.category,
    required this.priceCents,
    required this.currency,
    this.description = '',
    this.unit,
  });
  final String id;
  final String name;
  final String category; // service|hardware|subscription|input|report
  final int priceCents;
  final String currency;
  final String description;
  final String? unit;

  String get priceLabel => '${(priceCents / 100).toStringAsFixed(2)} $currency';

  factory GvProduct.fromJson(Map<String, dynamic> j) => GvProduct(
        id: j['id'].toString(),
        name: (j['name'] ?? '').toString(),
        category: (j['category'] ?? 'service').toString(),
        priceCents: (j['price_cents'] as num?)?.toInt() ?? 0,
        currency: (j['currency'] ?? 'USD').toString(),
        description: (j['description'] ?? '').toString(),
        unit: j['unit'] as String?,
      );
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
  });
  final String id;
  final DateTime createdAt;
  final int totalCents;
  final String currency;
  final String status; // quote|confirmed|fulfilled|cancelled
  final String paymentStatus; // unpaid|pending|paid|refunded
  final List<String> items;

  String get totalLabel => '${(totalCents / 100).toStringAsFixed(2)} $currency';
}
