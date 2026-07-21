import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import '../domain/product.dart';

class OrderDetailScreen extends ConsumerWidget {
  const OrderDetailScreen({required this.orderId, super.key});
  final String orderId;
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        appBar: AppBar(title: const Text('Detalhes do pedido')),
        body: ref.watch(ordersProvider).when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('$e')),
              data: (orders) {
                final order = orders.where((o) => o.id == orderId).firstOrNull;
                if (order == null) {
                  return const Center(child: Text('Pedido não encontrado.'));
                }
                return ListView(
                    padding: const EdgeInsets.all(GvSpacing.lg),
                    children: [
                      Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(order.id.toUpperCase(),
                                      style: const TextStyle(
                                          fontSize: 19,
                                          fontWeight: FontWeight.w800)),
                                  Text(
                                      DateFormat.yMMMd()
                                          .format(order.createdAt),
                                      style: const TextStyle(
                                          color: GvColors.textMuted))
                                ]),
                            Chip(
                                label: Text(
                                    order.delivery?.status ?? order.status)),
                          ]),
                      const SizedBox(height: 16),
                      GvCard(
                          child: Column(children: [
                        for (final item in order.items)
                          ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.check_circle_outline,
                                  color: GvColors.accentGreen),
                              title: Text(item)),
                        const Divider(),
                        Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('Total',
                                  style:
                                      TextStyle(fontWeight: FontWeight.w800)),
                              Text(
                                  StoreMoney.formatUsdCents(order.totalCents,
                                      ref.watch(storeCurrencyProvider)),
                                  style: const TextStyle(
                                      color: GvColors.accentCyan,
                                      fontWeight: FontWeight.w800))
                            ]),
                      ])),
                      if (order.delivery != null) ...[
                        const SizedBox(height: 14),
                        GvCard(
                            child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                              const Text('Entrega',
                                  style:
                                      TextStyle(fontWeight: FontWeight.w800)),
                              const SizedBox(height: 8),
                              Text(order.delivery!.destination,
                                  style: const TextStyle(
                                      color: GvColors.textSecondary)),
                              const SizedBox(height: 10),
                              LinearProgressIndicator(
                                  value: order.delivery!.progress,
                                  minHeight: 7,
                                  borderRadius: BorderRadius.circular(8)),
                              const SizedBox(height: 8),
                              Text(
                                  'Previsão: ${DateFormat.MMMd().add_Hm().format(order.delivery!.estimatedArrival)}',
                                  style: const TextStyle(
                                      color: GvColors.textMuted, fontSize: 12)),
                            ])),
                        const SizedBox(height: 14),
                        FilledButton.icon(
                            onPressed: () =>
                                context.go('/orders/${order.id}/tracking'),
                            icon: const Icon(Icons.map_outlined),
                            label: const Text('Acompanhar entrega')),
                      ],
                    ]);
              },
            ),
      );
}

class DeliveryTrackingScreen extends ConsumerWidget {
  const DeliveryTrackingScreen({required this.orderId, super.key});
  final String orderId;
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        appBar: AppBar(title: const Text('Acompanhar entrega')),
        body: ref.watch(ordersProvider).when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('$e')),
              data: (orders) {
                final order = orders.where((o) => o.id == orderId).firstOrNull;
                final delivery = order?.delivery;
                if (delivery == null) {
                  return const Center(
                      child:
                          Text('Este pedido não possui entrega rastreável.'));
                }
                return Column(children: [
                  Expanded(child: _DemoRouteMap(delivery: delivery)),
                  Container(
                    padding: const EdgeInsets.all(GvSpacing.lg),
                    decoration: const BoxDecoration(
                        color: GvColors.surface,
                        borderRadius:
                            BorderRadius.vertical(top: Radius.circular(24))),
                    child: SafeArea(
                        top: false,
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(children: [
                                const Icon(Icons.local_shipping,
                                    color: GvColors.accentGreen),
                                const SizedBox(width: 10),
                                Expanded(
                                    child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                      Text(delivery.status,
                                          style: const TextStyle(
                                              fontSize: 18,
                                              fontWeight: FontWeight.w800)),
                                      Text(delivery.trackingCode,
                                          style: const TextStyle(
                                              color: GvColors.textMuted))
                                    ])),
                                Text(
                                    DateFormat.Hm()
                                        .format(delivery.estimatedArrival),
                                    style: const TextStyle(
                                        fontSize: 19,
                                        fontWeight: FontWeight.w800))
                              ]),
                              const SizedBox(height: 14),
                              const _TimelineStep(
                                  label: 'Pedido confirmado', complete: true),
                              const _TimelineStep(
                                  label: 'Separado e preparado',
                                  complete: true),
                              const _TimelineStep(
                                  label: 'Em trânsito', complete: true),
                              const _TimelineStep(
                                  label: 'Saiu para entrega', complete: false),
                              const _TimelineStep(
                                  label: 'Entregue',
                                  complete: false,
                                  last: true),
                              const SizedBox(height: 8),
                              Text(delivery.destination,
                                  style: const TextStyle(
                                      color: GvColors.textSecondary,
                                      fontSize: 12)),
                              const SizedBox(height: 8),
                              const Text(
                                  'Mapa demonstrativo · preparado para Google Maps e API logística',
                                  style: TextStyle(
                                      color: GvColors.textMuted, fontSize: 10)),
                            ])),
                  ),
                ]);
              },
            ),
      );
}

class _DemoRouteMap extends StatelessWidget {
  const _DemoRouteMap({required this.delivery});
  final GvDelivery delivery;
  @override
  Widget build(BuildContext context) => Stack(children: [
        Positioned.fill(child: CustomPaint(painter: _MapPainter())),
        const Positioned(
            left: 36,
            top: 100,
            child:
                _MapPin(icon: Icons.inventory_2, color: GvColors.accentCyan)),
        const Positioned(
            right: 40,
            bottom: 82,
            child: _MapPin(icon: Icons.location_on, color: GvColors.critical)),
        Positioned(
            left: MediaQuery.sizeOf(context).width * .48,
            top: 200,
            child: const _MapPin(
                icon: Icons.local_shipping, color: GvColors.accentGreen)),
        Positioned(
            left: 16,
            top: 16,
            right: 16,
            child: GvCard(
                child: Row(children: [
              const Icon(Icons.route, color: GvColors.accentCyan),
              const SizedBox(width: 10),
              Expanded(
                  child: Text(
                      '${delivery.status} · chegada estimada ${DateFormat.Hm().format(delivery.estimatedArrival)}'))
            ]))),
      ]);
}

class _MapPin extends StatelessWidget {
  const _MapPin({required this.icon, required this.color});
  final IconData icon;
  final Color color;
  @override
  Widget build(BuildContext context) => Container(
      width: 44,
      height: 44,
      decoration: BoxDecoration(
          color: color,
          shape: BoxShape.circle,
          boxShadow: const [BoxShadow(color: Colors.black45, blurRadius: 8)]),
      child: Icon(icon, color: Colors.white, size: 22));
}

class _MapPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(
        Offset.zero & size, Paint()..color = const Color(0xFF0C1820));
    final road = Paint()
      ..color = const Color(0xFF263943)
      ..strokeWidth = 9
      ..style = PaintingStyle.stroke;
    final minor = Paint()
      ..color = const Color(0xFF182B32)
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;
    for (var y = 85.0; y < size.height; y += 76) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y - 44), minor);
    }
    for (var x = 45.0; x < size.width; x += 92) {
      canvas.drawLine(Offset(x, 0), Offset(x + 38, size.height), minor);
    }
    final path = Path()
      ..moveTo(56, 122)
      ..cubicTo(
          size.width * .25, 165, size.width * .6, 180, size.width * .55, 245)
      ..cubicTo(size.width * .53, 310, size.width * .82, 330, size.width - 58,
          size.height - 102);
    canvas.drawPath(path, road);
    canvas.drawPath(
        path,
        Paint()
          ..color = GvColors.accentGreen
          ..strokeWidth = 4
          ..style = PaintingStyle.stroke);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _TimelineStep extends StatelessWidget {
  const _TimelineStep(
      {required this.label, required this.complete, this.last = false});
  final String label;
  final bool complete;
  final bool last;
  @override
  Widget build(BuildContext context) =>
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
            width: 24,
            child: Column(children: [
              Icon(complete ? Icons.check_circle : Icons.radio_button_unchecked,
                  size: 17,
                  color: complete ? GvColors.accentGreen : GvColors.textMuted),
              if (!last)
                Container(
                    width: 2,
                    height: 17,
                    color:
                        complete ? GvColors.accentGreen : GvColors.borderStrong)
            ])),
        const SizedBox(width: 8),
        Text(label,
            style: TextStyle(
                color: complete ? GvColors.textPrimary : GvColors.textMuted,
                fontSize: 12)),
      ]);
}
