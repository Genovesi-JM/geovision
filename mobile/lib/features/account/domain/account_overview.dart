class AccountOverview {
  const AccountOverview({
    required this.organisationName,
    required this.plan,
    required this.status,
    required this.currency,
    required this.outstandingCents,
    required this.paidPayments,
    required this.pendingPayments,
    required this.sites,
    required this.orders,
    required this.activeOrders,
    required this.serviceRequests,
    required this.activeRequests,
    required this.lastUpdatedAt,
    this.recentOrders = const [],
  });

  final String organisationName;
  final String plan;
  final String status;
  final String currency;
  final int outstandingCents;
  final int paidPayments;
  final int pendingPayments;
  final int sites;
  final int orders;
  final int activeOrders;
  final int serviceRequests;
  final int activeRequests;
  final DateTime lastUpdatedAt;
  final List<AccountOrderSummary> recentOrders;

  factory AccountOverview.fromJson(Map<String, dynamic> json) {
    final organisation =
        Map<String, dynamic>.from(json['organisation'] as Map? ?? const {});
    final financial =
        Map<String, dynamic>.from(json['financial'] as Map? ?? const {});
    final activity =
        Map<String, dynamic>.from(json['activity'] as Map? ?? const {});
    return AccountOverview(
      organisationName: '${organisation['name'] ?? 'GeoVision'}',
      plan: '${organisation['plan'] ?? 'trial'}',
      status: '${organisation['status'] ?? 'active'}',
      currency: '${financial['currency'] ?? 'AOA'}',
      outstandingCents: (financial['outstanding_cents'] as num?)?.toInt() ?? 0,
      paidPayments: (financial['paid_payments'] as num?)?.toInt() ?? 0,
      pendingPayments: (financial['pending_payments'] as num?)?.toInt() ?? 0,
      sites: (activity['sites'] as num?)?.toInt() ?? 0,
      orders: (activity['orders'] as num?)?.toInt() ?? 0,
      activeOrders: (activity['active_orders'] as num?)?.toInt() ?? 0,
      serviceRequests: (activity['service_requests'] as num?)?.toInt() ?? 0,
      activeRequests: (activity['active_requests'] as num?)?.toInt() ?? 0,
      recentOrders: (json['recent_orders'] as List? ?? const [])
          .whereType<Map>()
          .map((row) =>
              AccountOrderSummary.fromJson(Map<String, dynamic>.from(row)))
          .toList(),
      lastUpdatedAt: DateTime.tryParse('${json['last_updated_at'] ?? ''}') ??
          DateTime.now(),
    );
  }
}

class AccountOrderSummary {
  const AccountOrderSummary(
      {required this.id,
      required this.number,
      required this.status,
      required this.totalCents,
      required this.currency});
  final String id;
  final String number;
  final String status;
  final int totalCents;
  final String currency;

  factory AccountOrderSummary.fromJson(Map<String, dynamic> json) =>
      AccountOrderSummary(
        id: '${json['id'] ?? ''}',
        number: '${json['number'] ?? ''}',
        status: '${json['status'] ?? 'pending'}',
        totalCents: (json['total_cents'] as num?)?.toInt() ?? 0,
        currency: '${json['currency'] ?? 'AOA'}',
      );
}
