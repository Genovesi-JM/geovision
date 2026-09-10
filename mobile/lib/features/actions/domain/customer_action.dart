enum CustomerActionBucket { critical, attention, scheduled, completed }

extension CustomerActionBucketLabel on CustomerActionBucket {
  String get label => switch (this) {
        CustomerActionBucket.critical => 'Critical',
        CustomerActionBucket.attention => 'Attention',
        CustomerActionBucket.scheduled => 'Scheduled',
        CustomerActionBucket.completed => 'Completed',
      };
}

class CustomerAction {
  const CustomerAction({
    required this.id,
    required this.assetId,
    required this.title,
    required this.description,
    required this.priority,
    required this.status,
    required this.lifecycleVersion,
    required this.createdAt,
    this.dueDate,
    this.recommendedCatalogItemId,
    this.completedAt,
  });

  final String id;
  final String assetId;
  final String title;
  final String description;
  final String priority;
  final String status;
  final int lifecycleVersion;
  final DateTime createdAt;
  final DateTime? dueDate;
  final String? recommendedCatalogItemId;
  final DateTime? completedAt;

  factory CustomerAction.fromJson(Map<String, dynamic> json) => CustomerAction(
        id: '${json['id'] ?? ''}',
        assetId: '${json['asset_id'] ?? ''}',
        title: '${json['title'] ?? ''}',
        description: '${json['description'] ?? ''}',
        priority: '${json['priority'] ?? 'MEDIUM'}'.toUpperCase(),
        status: '${json['status'] ?? 'OPEN'}'.toUpperCase(),
        lifecycleVersion: (json['lifecycle_version'] as num?)?.toInt() ?? 1,
        createdAt: DateTime.tryParse('${json['created_at'] ?? ''}') ??
            DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
        dueDate: DateTime.tryParse('${json['due_date'] ?? ''}'),
        recommendedCatalogItemId:
            json['recommended_catalog_item_id']?.toString(),
        completedAt: DateTime.tryParse('${json['completed_at'] ?? ''}'),
      );
}

class CustomerActionBuckets {
  const CustomerActionBuckets({
    this.critical = const [],
    this.attention = const [],
    this.scheduled = const [],
    this.completed = const [],
  });

  final List<CustomerAction> critical;
  final List<CustomerAction> attention;
  final List<CustomerAction> scheduled;
  final List<CustomerAction> completed;

  List<CustomerAction> get all => [
        ...critical,
        ...attention,
        ...scheduled,
        ...completed,
      ];

  List<CustomerAction> items(CustomerActionBucket bucket) => switch (bucket) {
        CustomerActionBucket.critical => critical,
        CustomerActionBucket.attention => attention,
        CustomerActionBucket.scheduled => scheduled,
        CustomerActionBucket.completed => completed,
      };

  factory CustomerActionBuckets.fromJson(dynamic json) {
    if (json is List) return CustomerActionBuckets.fromItems(_items(json));
    final body = Map<String, dynamic>.from(json as Map? ?? const {});
    final rawBuckets = body['buckets'] is Map
        ? Map<String, dynamic>.from(body['buckets'] as Map)
        : body;
    if (rawBuckets.keys.any((key) => const {
          'critical',
          'attention',
          'scheduled',
          'completed'
        }.contains(key))) {
      return CustomerActionBuckets(
        critical: _items(rawBuckets['critical']),
        attention: _items(rawBuckets['attention']),
        scheduled: _items(rawBuckets['scheduled']),
        completed: _items(rawBuckets['completed']),
      );
    }
    return CustomerActionBuckets.fromItems(_items(body['items']));
  }

  factory CustomerActionBuckets.fromItems(List<CustomerAction> items) {
    final now = DateTime.now().toUtc();
    final critical = <CustomerAction>[];
    final attention = <CustomerAction>[];
    final scheduled = <CustomerAction>[];
    final completed = <CustomerAction>[];
    for (final item in items) {
      if (item.status == 'COMPLETED') {
        completed.add(item);
      } else if (item.priority == 'CRITICAL' || item.priority == 'URGENT') {
        critical.add(item);
      } else if (item.dueDate != null && item.dueDate!.isAfter(now)) {
        scheduled.add(item);
      } else if (item.status != 'CANCELLED' && item.status != 'DISMISSED') {
        attention.add(item);
      }
    }
    return CustomerActionBuckets(
      critical: critical,
      attention: attention,
      scheduled: scheduled,
      completed: completed,
    );
  }
}

List<CustomerAction> _items(dynamic raw) => (raw as List? ?? const [])
    .whereType<Map>()
    .map((item) => CustomerAction.fromJson(Map<String, dynamic>.from(item)))
    .where((item) => item.id.isNotEmpty && item.assetId.isNotEmpty)
    .toList();
