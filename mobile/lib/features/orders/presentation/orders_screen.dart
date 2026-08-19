import 'package:flutter/material.dart';
import '../../../l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../../core/widgets/gv_states.dart';
import '../../authentication/presentation/auth_controller.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import '../domain/product.dart';
import 'cart_controller.dart';
import 'product_image.dart';
import 'store_copy.dart';

class OrdersScreen extends ConsumerStatefulWidget {
  const OrdersScreen({super.key});
  @override
  ConsumerState<OrdersScreen> createState() => _OrdersScreenState();
}

class _OrdersScreenState extends ConsumerState<OrdersScreen> {
  static const _storeSectors = {
    'agro', 'environment', 'construction', 'industry', 'infrastructure'
  };
  String category = 'all';
  String sector = 'all';
  String query = '';
  bool showOrders = false;

  @override
  void initState() {
    super.initState();
    // Recommend the account's own sector first; fall back to all sectors when
    // unknown.
    final profile = ref.read(authControllerProvider).profile;
    sector = (profile?.sectors ?? const <String>[])
        .map((e) => e.toLowerCase())
        .firstWhere(_storeSectors.contains, orElse: () => 'all');
  }

  @override
  Widget build(BuildContext context) {
    final catalogue = ref.watch(catalogueProvider);
    final orders = ref.watch(ordersProvider);
    final l10n = AppLocalizations.of(context);
    final copy = StoreCopy.of(context);
    final language = Localizations.localeOf(context).languageCode;
    final cartCount =
        ref.watch(cartProvider).fold<int>(0, (s, l) => s + l.quantity);
    final currency = ref.watch(storeCurrencyProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(copy.title),
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
                  ref.read(cartProvider.notifier).changeCurrency(value);
                }
              },
            ),
          ),
          Badge(
            isLabelVisible: cartCount > 0,
            label: Text('$cartCount'),
            child: IconButton(
              tooltip: copy.cart,
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
          _CommerceHero(
              copy: copy, onOrders: () => setState(() => showOrders = true)),
          const SizedBox(height: GvSpacing.md),
          SegmentedButton<bool>(
            segments: [
              ButtonSegment(
                  value: false,
                  label: Text(copy.shop),
                  icon: const Icon(Icons.storefront)),
              ButtonSegment(
                  value: true,
                  label: Text(copy.orders),
                  icon: const Icon(Icons.local_shipping_outlined)),
            ],
            selected: {showOrders},
            onSelectionChanged: (value) =>
                setState(() => showOrders = value.first),
          ),
          const SizedBox(height: GvSpacing.lg),
          if (!showOrders) ...[
            TextField(
              onChanged: (value) => setState(() => query = value.trim()),
              decoration: InputDecoration(
                hintText: l10n.searchProducts,
                prefixIcon: const Icon(Icons.search),
              ),
            ),
            const SizedBox(height: GvSpacing.md),
            SizedBox(
              height: 38,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: {
                  'all': copy.all,
                  'hardware': copy.hardware,
                  'service': copy.services,
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
            const SizedBox(height: GvSpacing.sm),
            SizedBox(
              height: 34,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: {
                  'all': copy.allSectors,
                  'agro': copy.sector('agro'),
                  'environment': copy.sector('environment'),
                  'construction': copy.sector('construction'),
                  'industry': copy.sector('industry'),
                  'infrastructure': copy.sector('infrastructure'),
                }
                    .entries
                    .map((entry) => Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: FilterChip(
                            label: Text(entry.value),
                            selected: sector == entry.key,
                            onSelected: (_) =>
                                setState(() => sector = entry.key),
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
                final normalizedQuery = query.toLowerCase();
                final filtered = products.where((product) {
                  final categoryMatches =
                      category == 'all' || product.category == category;
                  final sectorMatches =
                      sector == 'all' || product.sectors.contains(sector);
                  final queryMatches = normalizedQuery.isEmpty ||
                      product
                          .localizedName(language)
                          .toLowerCase()
                          .contains(normalizedQuery) ||
                      product
                          .localizedDescription(language)
                          .toLowerCase()
                          .contains(normalizedQuery);
                  return categoryMatches && sectorMatches && queryMatches;
                }).toList();
                if (filtered.isEmpty) {
                  return GvCard(
                    child: Text(
                      copy.empty,
                      style: const TextStyle(color: GvColors.textSecondary),
                    ),
                  );
                }
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
                  itemBuilder: (_, i) => _ProductCard(
                      product: filtered[i], copy: copy, language: language),
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
                                        StoreMoney.formatOrder(
                                            o.totalCents, o.currency),
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w700)),
                                    if (o.delivery != null)
                                      Text(copy.tracking,
                                          style: const TextStyle(
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
  const _CommerceHero({required this.copy, required this.onOrders});
  final StoreCopy copy;
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
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(copy.hero,
                    style: const TextStyle(
                        fontSize: 19, fontWeight: FontWeight.w800)),
                const SizedBox(height: 5),
                Text(copy.heroBody,
                    style: const TextStyle(
                        color: GvColors.textSecondary, fontSize: 12)),
              ])),
          IconButton.filled(
              onPressed: onOrders, icon: const Icon(Icons.arrow_forward)),
        ]),
      );
}

class _ProductCard extends ConsumerWidget {
  const _ProductCard(
      {required this.product, required this.copy, required this.language});
  final GvProduct product;
  final StoreCopy copy;
  final String language;
  @override
  Widget build(BuildContext context, WidgetRef ref) => GvCard(
        padding: EdgeInsets.zero,
        onTap: () => context.go('/orders/product/${product.id}'),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(
            child: ProductImage(
              product: product,
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(15)),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(11),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(product.localizedName(language),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 13)),
              const SizedBox(height: 5),
              Text(
                  StoreMoney.formatProduct(
                      product, ref.watch(storeCurrencyProvider)),
                  style: const TextStyle(
                      color: GvColors.accentCyan, fontWeight: FontWeight.w800)),
              Row(children: [
                Expanded(
                    child: Text(copy.inStock,
                        style: const TextStyle(
                            color: GvColors.accentGreen, fontSize: 10))),
                IconButton.filledTonal(
                  visualDensity: VisualDensity.compact,
                  onPressed: () {
                    ref.read(cartProvider.notifier).add(product);
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content:
                            Text(copy.added(product.localizedName(language)))));
                  },
                  icon: const Icon(Icons.add, size: 17),
                ),
              ]),
            ]),
          ),
        ]),
      );
}
