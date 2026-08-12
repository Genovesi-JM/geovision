class GvProduct {
  const GvProduct({
    required this.id,
    required this.name,
    required this.category,
    required this.priceCents,
    required this.currency,
    this.priceAkzCents,
    this.priceEurCents,
    this.description = '',
    this.unit,
    this.stockStatus = 'in_stock',
    this.featured = false,
    this.sectors = const [],
    this.deliverables = const [],
    this.indicativePrice = true,
    this.image,
    this.translations = const {},
  });
  final String id;
  final String name;
  final String category; // service|hardware|subscription|input|report
  final int priceCents;
  final String currency;
  final int? priceAkzCents;
  final int? priceEurCents;
  final String description;
  final String? unit;
  final String stockStatus;
  final bool featured;
  final List<String> sectors;
  final List<String> deliverables;
  final bool indicativePrice;

  /// Bundled asset path in demo mode or HTTPS URL supplied by the commerce API.
  final String? image;
  final Map<String, Map<String, dynamic>> translations;

  String localizedName(String languageCode) =>
      translations[languageCode]?['name']?.toString() ??
      translations['pt']?['name']?.toString() ??
      name;

  String localizedDescription(String languageCode) =>
      translations[languageCode]?['description']?.toString() ??
      translations['pt']?['description']?.toString() ??
      description;

  List<String> localizedDeliverables(String languageCode) {
    final translated = translations[languageCode]?['deliverables'];
    if (translated is List) {
      return translated.map((item) => item.toString()).toList();
    }
    if (languageCode == 'pt') return deliverables;
    final kind = category == 'service' ? 'service' : 'hardware';
    const generic = {
      'service': {
        'en': [
          'Mapped visual evidence',
          'Technical summary',
          'Agreed output files'
        ],
        'es': [
          'Evidencia visual cartografiada',
          'Resumen técnico',
          'Archivos de entrega acordados'
        ],
        'fr': [
          'Preuves visuelles cartographiées',
          'Synthèse technique',
          'Fichiers de livraison convenus'
        ],
      },
      'hardware': {
        'en': ['Selected hardware', 'Connection guide', 'Compatibility check'],
        'es': [
          'Hardware seleccionado',
          'Guía de conexión',
          'Verificación de compatibilidad'
        ],
        'fr': [
          'Matériel sélectionné',
          'Guide de connexion',
          'Vérification de compatibilité'
        ],
      },
    };
    return generic[kind]?[languageCode] ?? deliverables;
  }

  String get priceLabel => '${(priceCents / 100).toStringAsFixed(2)} $currency';

  factory GvProduct.fromJson(Map<String, dynamic> j) => GvProduct(
        id: j['id'].toString(),
        name: (j['name'] ?? '').toString(),
        category: _mobileCategory(j),
        priceCents: (j['price_cents'] as num?)?.toInt() ??
            (j['price_usd'] as num?)?.toInt() ??
            0,
        currency: (j['currency'] ?? 'USD').toString(),
        priceAkzCents: (j['price'] as num?)?.toInt(),
        priceEurCents: (j['price_eur'] as num?)?.toInt(),
        description: (j['description'] ?? '').toString(),
        unit: (j['unit'] ?? j['unit_label']) as String?,
        stockStatus: (j['stock_status'] ?? 'in_stock').toString(),
        featured: j['featured'] == true || j['is_featured'] == true,
        sectors: (j['sectors'] as List?)?.map((v) => v.toString()).toList() ??
            const [],
        deliverables:
            (j['deliverables'] as List?)?.map((v) => v.toString()).toList() ??
                const [],
        indicativePrice: j['indicative_price'] != false,
        image: (j['image_url'] ?? j['image'])?.toString(),
        translations: (j['translations'] as Map?)?.map((key, value) => MapEntry(
                  key.toString(),
                  value is Map
                      ? Map<String, dynamic>.from(value)
                      : <String, dynamic>{},
                )) ??
            const {},
      );

  static String _mobileCategory(Map<String, dynamic> json) {
    final type = (json['product_type'] ?? '').toString();
    final category = (json['category'] ?? '').toString();
    if (const [
      'service',
      'hardware',
      'equipment',
      'seeds',
      'inputs',
      'subscription'
    ].contains(type)) {
      return type;
    }
    if (category == 'flight') return 'service';
    return category.isEmpty ? 'service' : category;
  }
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
