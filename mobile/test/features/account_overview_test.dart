import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/features/account/domain/account_overview.dart';

void main() {
  test('account overview maps backend snapshot without losing money precision',
      () {
    final model = AccountOverview.fromJson({
      'organisation': {
        'name': 'GeoVision Client',
        'plan': 'business',
        'status': 'active'
      },
      'financial': {
        'currency': 'AOA',
        'outstanding_cents': 5424500,
        'paid_payments': 3,
        'pending_payments': 1
      },
      'activity': {
        'sites': 2,
        'orders': 4,
        'active_orders': 1,
        'service_requests': 5,
        'active_requests': 2
      },
      'recent_orders': [
        {
          'id': 'o1',
          'number': 'GV-001',
          'status': 'dispatched',
          'total_cents': 5424500,
          'currency': 'AOA'
        }
      ],
      'last_updated_at': '2026-07-22T10:00:00',
    });

    expect(model.organisationName, 'GeoVision Client');
    expect(model.outstandingCents, 5424500);
    expect(model.activeRequests, 2);
    expect(model.recentOrders.single.number, 'GV-001');
  });
}
