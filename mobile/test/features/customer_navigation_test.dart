import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/routing/customer_routes.dart';
import 'package:geovision/features/account/domain/customer_experience.dart';
import 'package:geovision/features/actions/domain/customer_action.dart';
import 'package:geovision/features/assets/domain/customer_asset.dart';
import 'package:geovision/features/home/domain/home_summary.dart';

void main() {
  test('experience parses server-owned capabilities and workspace context', () {
    final experience = CustomerExperience.fromJson({
      'active_workspace_id': 'workspace-2',
      'active_organization_id': 'organization-1',
      'permissions': ['asset:read'],
      'capabilities': {
        'assets': true,
        'actions': false,
        'services': true,
      },
      'workspaces': [
        {
          'id': 'workspace-2',
          'organization_id': 'organization-1',
          'name': 'Port operations',
          'organization_name': 'Customer One',
          'role': 'member',
          'sector': 'PORTS_INDUSTRIAL',
          'modules_enabled': ['assets', 'services'],
        },
      ],
    });

    expect(experience.activeWorkspace?.name, 'Port operations');
    expect(experience.hasCapability('assets'), isTrue);
    expect(experience.hasCapability('services'), isTrue);
    expect(experience.hasCapability('actions'), isFalse);
    expect(experience.hasCapability('billing'), isFalse,
        reason: 'Missing capability flags must fail closed.');
  });

  test('typed customer targets resolve only to allowlisted exact routes', () {
    expect(CustomerRoutes.forTarget('asset', 'asset-1'), '/assets/asset-1');
    expect(CustomerRoutes.forTarget('action', 'action-1'), '/actions/action-1');
    expect(CustomerRoutes.forTarget('service', 'service-1'),
        '/services/service-1');
    expect(CustomerRoutes.forTarget('order', 'order-1'),
        '/services/orders/order-1');
    expect(CustomerRoutes.forTarget('service_result', 'result-1'),
        '/work/result-1');
    expect(CustomerRoutes.forTarget('report', 'report-1'), '/reports/report-1');
    expect(CustomerRoutes.forTarget('asset', '../../other-workspace'), isNull);
    expect(CustomerRoutes.forTarget('unknown', 'target-1'), isNull);
  });

  test('invitation paths are canonicalized and arbitrary paths are ignored',
      () {
    expect(
      CustomerRoutes.forInvitation(
        kind: 'asset',
        targetId: 'asset-1',
        path: '/sites/asset-1',
      ),
      '/assets/asset-1',
    );
    expect(
      CustomerRoutes.forInvitation(
        kind: 'service_result',
        targetId: 'request-1',
        path: '/work/request-1',
      ),
      '/work/request-1',
    );
    expect(
      CustomerRoutes.forInvitation(
        kind: 'order',
        targetId: 'order-1',
        path: 'https://example.test/steal',
      ),
      '/services/orders/order-1',
    );
  });

  test('home projection drops priority items with unsafe target identifiers',
      () {
    final summary = HomeSummary.fromJson({
      'workspace_id': 'workspace-1',
      'organization_name': 'Customer',
      'workspace_name': 'Mine',
      'attention': {},
      'priority_items': [
        {
          'id': 'safe',
          'target_type': 'ACTION',
          'target_id': 'action-1',
          'title': 'Review',
          'summary': 'Review the result',
        },
        {
          'id': 'unsafe',
          'target_type': 'ACTION',
          'target_id': '../action-2',
          'title': 'Unsafe',
          'summary': 'Must not render',
        },
      ],
      'updated_at': '2026-09-10T12:00:00Z',
    });

    expect(summary.priorityItems.map((item) => item.id), ['safe']);
    expect(summary.priorityItems.single.appPath, '/actions/action-1');
  });

  test('actions are projected into the four customer buckets', () {
    final buckets = CustomerActionBuckets.fromJson({
      'items': [
        _action('critical', priority: 'CRITICAL'),
        _action('attention', priority: 'HIGH'),
        _action('scheduled', dueDate: '2999-01-01T00:00:00Z'),
        _action('completed', status: 'COMPLETED'),
      ],
    });

    expect(buckets.critical.single.id, 'critical');
    expect(buckets.attention.single.id, 'attention');
    expect(buckets.scheduled.single.id, 'scheduled');
    expect(buckets.completed.single.id, 'completed');
  });

  test('canonical assets parse cross-sector type and spatial center', () {
    final asset = CustomerAsset.fromJson({
      'id': 'bridge-1',
      'name': 'Bridge One',
      'sector': 'INFRASTRUCTURE',
      'asset_type': 'BRIDGE',
      'status': 'active',
      'location_label': 'Luanda',
      'geometry': {
        'type': 'Point',
        'coordinates': [13.2, -8.8],
      },
      'metadata': {'span_m': 420},
    });

    expect(asset.assetType, 'BRIDGE');
    expect(asset.sector, 'INFRASTRUCTURE');
    expect(asset.hasLocation, isTrue);
    expect(asset.latitude, -8.8);
    expect(asset.longitude, 13.2);
  });
}

Map<String, dynamic> _action(
  String id, {
  String priority = 'MEDIUM',
  String status = 'OPEN',
  String? dueDate,
}) =>
    {
      'id': id,
      'asset_id': 'asset-1',
      'title': id,
      'description': id,
      'priority': priority,
      'status': status,
      'created_at': '2026-09-10T12:00:00Z',
      if (dueDate != null) 'due_date': dueDate,
    };
