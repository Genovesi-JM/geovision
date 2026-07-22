import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import '../domain/product.dart';
import 'cart_controller.dart';
import 'product_image.dart';

class ProductDetailScreen extends ConsumerWidget {
  const ProductDetailScreen({required this.productId, super.key});
  final String productId;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalogue = ref.watch(catalogueProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Detalhes do produto'), actions: [
        IconButton(
            tooltip: 'Perguntar à GAIA sobre este produto',
            onPressed: () =>
                context.go('/assistant?from=store&product=$productId'),
            icon: const Icon(Icons.auto_awesome)),
        IconButton(
            onPressed: () => context.go('/orders/cart'),
            icon: const Icon(Icons.shopping_cart_outlined))
      ]),
      body: catalogue.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('$e')),
        data: (products) {
          final product = products.where((p) => p.id == productId).firstOrNull;
          if (product == null) {
            return const Center(child: Text('Produto não encontrado.'));
          }
          return _ProductBody(product: product);
        },
      ),
    );
  }
}

class _ProductBody extends ConsumerWidget {
  const _ProductBody({required this.product});
  final GvProduct product;
  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      ListView(padding: const EdgeInsets.all(GvSpacing.lg), children: [
        SizedBox(
          height: 230,
          child: ProductImage(
            product: product,
            borderRadius: BorderRadius.circular(22),
          ),
        ),
        const SizedBox(height: 20),
        Row(children: [
          Expanded(
              child: Text(product.name,
                  style: const TextStyle(
                      fontSize: 23, fontWeight: FontWeight.w800))),
          const Chip(label: Text('Em stock'))
        ]),
        const SizedBox(height: 8),
        Text(
            StoreMoney.formatProduct(product, ref.watch(storeCurrencyProvider)),
            style: const TextStyle(
                fontSize: 21,
                color: GvColors.accentCyan,
                fontWeight: FontWeight.w800)),
        if (product.unit != null)
          Text('por ${product.unit}',
              style: const TextStyle(color: GvColors.textMuted)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: StoreCurrency.values
              .map((currency) => Chip(
                    label: Text(
                        '${currency.code}  ${StoreMoney.formatProduct(product, currency)}'),
                  ))
              .toList(),
        ),
        const SizedBox(height: 18),
        Text(product.description,
            style: const TextStyle(color: GvColors.textSecondary, height: 1.5)),
        const SizedBox(height: 20),
        if (product.deliverables.isNotEmpty) ...[
          const Text('Inclui',
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          const SizedBox(height: 8),
          ...product.deliverables.map((item) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(children: [
                  const Icon(Icons.check_circle,
                      size: 17, color: GvColors.accentGreen),
                  const SizedBox(width: 8),
                  Expanded(child: Text(item)),
                ]),
              )),
          const SizedBox(height: 16),
        ],
        const Wrap(spacing: 8, runSpacing: 8, children: [
          Chip(
              avatar: Icon(Icons.verified, size: 16),
              label: Text('Qualidade verificada')),
          Chip(
              avatar: Icon(Icons.local_shipping, size: 16),
              label: Text('Entrega rastreada')),
          Chip(
              avatar: Icon(Icons.support_agent, size: 16),
              label: Text('Suporte GeoVision'))
        ]),
        if (product.category == 'equipment' ||
            product.category == 'hardware') ...[
          const SizedBox(height: 18),
          OutlinedButton.icon(
            onPressed: () => context.go('/guides'),
            icon: const Icon(Icons.menu_book_outlined),
            label: const Text('Ver instalação, utilização e segurança'),
          ),
        ],
        const SizedBox(height: 28),
        FilledButton.icon(
            onPressed: () {
              ref.read(cartProvider.notifier).add(product);
              context.go('/orders/cart');
            },
            icon: const Icon(Icons.add_shopping_cart),
            label: const Text('Adicionar ao carrinho')),
      ]);
}
