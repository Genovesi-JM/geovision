import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_section_header.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/orders_repository.dart';
import '../domain/product.dart';

class OrdersScreen extends ConsumerWidget {
  const OrdersScreen({super.key});

  Color _payColor(String s) {
    switch (s) {
      case 'paid':
        return GvColors.accentGreen;
      case 'pending':
        return GvColors.medium;
      case 'refunded':
        return GvColors.textMuted;
      default:
        return GvColors.high;
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalogue = ref.watch(catalogueProvider);
    final orders = ref.watch(ordersProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Orders & catalogue')),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          const GvSectionHeader(title: 'Catalogue'),
          catalogue.when(
            loading: () => const GvLoading(),
            error: (e, _) => GvErrorState(message: '$e'),
            data: (products) => Column(
              children: products
                  .map((p) => Padding(
                        padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                        child: _ProductCard(product: p, ref: ref),
                      ))
                  .toList(),
            ),
          ),
          const SizedBox(height: GvSpacing.md),
          const GvSectionHeader(title: 'Order history'),
          orders.when(
            loading: () => const GvLoading(),
            error: (e, _) => GvErrorState(message: '$e'),
            data: (list) => Column(
              children: list
                  .map((o) => Padding(
                        padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                        child: GvCard(
                          child: Row(
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(o.items.join(', '),
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w600)),
                                    Text(
                                        '${DateFormat.yMMMd().format(o.createdAt.toLocal())} · ${o.status}',
                                        style: const TextStyle(
                                            color: GvColors.textMuted,
                                            fontSize: 12)),
                                  ],
                                ),
                              ),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(o.totalLabel,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w700)),
                                  Text(o.paymentStatus,
                                      style: TextStyle(
                                          color: _payColor(o.paymentStatus),
                                          fontSize: 12)),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ))
                  .toList(),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({required this.product, required this.ref});
  final GvProduct product;
  final WidgetRef ref;
  @override
  Widget build(BuildContext context) {
    return GvCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                  child: Text(product.name,
                      style: const TextStyle(fontWeight: FontWeight.w700))),
              Text(product.priceLabel,
                  style: const TextStyle(
                      color: GvColors.accentCyan, fontWeight: FontWeight.w700)),
            ],
          ),
          const SizedBox(height: 4),
          Text(product.description,
              style:
                  const TextStyle(color: GvColors.textSecondary, fontSize: 13)),
          const SizedBox(height: GvSpacing.sm),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton(
              onPressed: () => _requestQuote(context),
              child: const Text('Request'),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _requestQuote(BuildContext context) async {
    final repo = ref.read(ordersRepositoryProvider);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
          content:
              Text('Quote requested via ${repo.paymentProviderId} (demo).')),
    );
  }
}
