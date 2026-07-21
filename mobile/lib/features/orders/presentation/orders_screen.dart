import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import '../domain/product.dart';
import 'cart_controller.dart';

class OrdersScreen extends ConsumerStatefulWidget {
  const OrdersScreen({super.key});
  @override
  ConsumerState<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends ConsumerState<OrdersScreen> {
  String category = 'all';
  bool showOrders = false;

  @override
  Widget build(BuildContext context) {
    final catalogue = ref.watch(catalogueProvider);
    final orders = ref.watch(ordersProvider);
    final cartCount =
        ref.watch(cartProvider).fold<int>(0, (s, l) => s + l.quantity);
    final currency = ref.watch(storeCurrencyProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('GeoVision Store'),
        actions: [
          DropdownButtonHideUnderline(
            child: DropdownButton<StoreCurrency>(
              value: currency,
              items: StoreCurrency.values
                  .map((value) => DropdownMenuItem(
                        value: value,
                        child: Text(value.code,
                            style: const TextStyle(fontSize: 12)),
                      ))
                  .toList(),
              onChanged: (value) {
                if (value != null) {
                  ref.read(storeCurrencyProvider.notifier).state = value;
                }
              },
            ),
          ),
          Badge(
            isLabelVisible: cartCount > 0,
            label: Text('$cartCount'),
            child: IconButton(
              tooltip: 'Cart',
              onPressed: () => context.go('/orders/cart'),
              icon: const Icon(Icons.shopping_cart_outlined),
            ),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(GvSpacing.lg),
        children: [
          _CommerceHero(onOrders: () => setState(() => showOrders = true)),
          const SizedBox(height: GvSpacing.md),
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(
                  value: false,
                  label: Text('Loja'),
                  icon: Icon(Icons.storefront)),
              ButtonSegment(
                  value: true,
                  label: Text('Pedidos'),
                  icon: Icon(Icons.local_shipping_outlined)),
            ],
            selected: {showOrders},
            onSelectionChanged: (value) =>
                setState(() => showOrders = value.first),
          ),
          const SizedBox(height: GvSpacing.lg),
          if (!showOrders) ...[
            const TextField(
              decoration: InputDecoration(
                hintText: 'Pesquisar produtos e serviços…',
                prefixIcon: Icon(Icons.search),
              ),
            ),
            const SizedBox(height: GvSpacing.md),
            SizedBox(
              height: 38,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: {
                  'all': 'Todos',
                  'seeds': 'Sementes',
                  'inputs': 'Insumos',
                  'equipment': 'Equipamentos',
                  'hardware': 'Sensores & IoT',
                  'service': 'Serviços',
                }
                    .entries
                    .map((e) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: ChoiceChip(
                            label: Text(e.value),
                            selected: category == e.key,
                            onSelected: (_) => setState(() => category = e.key),
                          ),
                        ))
                    .toList(),
              ),
            ),
            const SizedBox(height: GvSpacing.md),
            catalogue.when(
              loading: () => const GvLoading(),
              error: (e, _) => GvErrorState(message: '$e'),
              data: (products) {
                final filtered = category == 'all'
                    ? products
                    : products.where((p) => p.category == category).toList();
                return GridView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    crossAxisSpacing: GvSpacing.sm,
                    mainAxisSpacing: GvSpacing.sm,
                    childAspectRatio: .73,
                  ),
                  itemCount: filtered.length,
                  itemBuilder: (_, i) => _ProductCard(product: filtered[i]),
                );
              },
            ),
          ] else
            orders.when(
              loading: () => const GvLoading(),
              error: (e, _) => GvErrorState(message: '$e'),
              data: (list) => Column(
                children: list
                    .map((o) => Padding(
                          padding: const EdgeInsets.only(bottom: GvSpacing.sm),
                          child: GvCard(
                            onTap: () => context.go('/orders/${o.id}'),
                            child: Row(children: [
                              Container(
                                width: 48,
                                height: 48,
                                decoration: BoxDecoration(
                                    color: GvColors.accentGreen
                                        .withValues(alpha: .12),
                                    borderRadius: BorderRadius.circular(12)),
                                child: Icon(
                                    o.delivery == null
                                        ? Icons.receipt_long
                                        : Icons.local_shipping,
                                    color: GvColors.accentGreen),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                  child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                    Text(o.id.toUpperCase(),
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w800)),
                                    Text(o.items.join(' · '),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(
                                            color: GvColors.textSecondary,
                                            fontSize: 12)),
                                    Text(
                                        '${DateFormat.yMMMd().format(o.createdAt)} · ${o.status}',
                                        style: const TextStyle(
                                            color: GvColors.textMuted,
                                            fontSize: 11)),
                                  ])),
                              Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text(
                                        StoreMoney.formatUsdCents(
                                            o.totalCents, currency),
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w700)),
                                    if (o.delivery != null)
                                      const Text('Track',
                                          style: TextStyle(
                                              color: GvColors.accentCyan,
                                              fontSize: 12)),
                                  ]),
                            ]),
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

class _CommerceHero extends StatelessWidget {
  const _CommerceHero({required this.onOrders});
  final VoidCallback onOrders;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
              colors: [Color(0xFF064E3B), Color(0xFF0B1428)]),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: GvColors.borderStrong),
        ),
        child: Row(children: [
          const Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text('Tudo para produzir melhor',
                    style:
                        TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
                SizedBox(height: 5),
                Text('Sementes, equipamentos, sensores e serviços GeoVision.',
                    style:
                        TextStyle(color: GvColors.textSecondary, fontSize: 12)),
              ])),
          IconButton.filled(
              onPressed: onOrders, icon: const Icon(Icons.arrow_forward)),
        ]),
      );
}

class _ProductCard extends ConsumerWidget {
  const _ProductCard({required this.product});
  final GvProduct product;
  IconData get icon => switch (product.category) {
        'seeds' => Icons.grass,
        'inputs' => Icons.science_outlined,
        'equipment' => Icons.agriculture,
        'hardware' => Icons.sensors,
        'service' => Icons.flight_takeoff,
        _ => Icons.inventory_2_outlined,
      };
  @override
  Widget build(BuildContext context, WidgetRef ref) => GvCard(
        padding: EdgeInsets.zero,
        onTap: () => context.go('/orders/product/${product.id}'),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
              child: Container(
            width: double.infinity,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    GvColors.accentGreen.withValues(alpha: .25),
                    GvColors.surfaceDeep
                  ]),
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(15)),
            ),
            child: Icon(icon, size: 56, color: GvColors.accentGreen),
          )),
          Padding(
            padding: const EdgeInsets.all(11),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(product.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 13)),
              const SizedBox(height: 5),
              Text(
                  StoreMoney.formatUsdCents(
                      product.priceCents, ref.watch(storeCurrencyProvider)),
                  style: const TextStyle(
                      color: GvColors.accentCyan, fontWeight: FontWeight.w800)),
              Row(children: [
                const Expanded(
                    child: Text('Em stock',
                        style: TextStyle(
                            color: GvColors.accentGreen, fontSize: 10))),
                IconButton.filledTonal(
                  visualDensity: VisualDensity.compact,
                  onPressed: () {
                    ref.read(cartProvider.notifier).add(product);
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content:
                            Text('${product.name} adicionado ao carrinho.')));
                  },
                  icon: const Icon(Icons.add, size: 17),
                ),
              ]),
            ]),
          ),
        ]),
      );
}
