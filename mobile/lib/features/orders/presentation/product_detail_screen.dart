import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/localization/journey_copy.dart';
import '../../../core/theme/app_spacing.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import '../domain/product.dart';
import 'cart_controller.dart';
import 'product_image.dart';
import 'store_copy.dart';

class ProductDetailScreen extends ConsumerWidget {
  const ProductDetailScreen({required this.productId, this.assetId, super.key});
  final String productId;
  final String? assetId;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final catalogue = ref.watch(catalogueProvider);
    final copy = StoreCopy.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(copy.details), actions: [
        IconButton(
            tooltip: copy.askGaia,
            onPressed: () =>
                context.go('/assistant?from=store&product=$productId'),
            icon: const Icon(Icons.auto_awesome)),
        IconButton(
            onPressed: () => context.push('/services/cart'),
            icon: const Icon(Icons.shopping_cart_outlined))
      ]),
      body: catalogue.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('$e')),
        data: (products) {
          final product = products.where((p) => p.id == productId).firstOrNull;
          if (product == null) {
            return Center(child: Text(copy.notFound));
          }
          return _ProductBody(product: product, assetId: assetId);
        },
      ),
    );
  }
}

class _ProductBody extends ConsumerWidget {
  const _ProductBody({required this.product, this.assetId});
  final GvProduct product;
  final String? assetId;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final copy = StoreCopy.of(context);
    final language = Localizations.localeOf(context).languageCode;
    final currency = ref.watch(storeCurrencyProvider);
    final enquiry = product.requiresEnquiry ||
        StoreMoney.productCents(product, currency) == null;
    return ListView(padding: const EdgeInsets.all(GvSpacing.lg), children: [
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
            child: Text(product.localizedName(language),
                style: const TextStyle(
                    fontSize: 23, fontWeight: FontWeight.w800))),
        if (!enquiry && product.stockStatus == 'in_stock')
          Chip(label: Text(copy.inStock))
      ]),
      if (product.stockStatus == 'unknown') Text(copy.availabilityUnknown),
      const SizedBox(height: 8),
      Text(
          product.priceModel.toUpperCase() == 'QUOTE'
              ? journeyText(context, 'Precio a consultar', 'Price on request',
                  pt: 'Preço sob consulta')
              : StoreMoney.formatProduct(product, currency,
                  unavailable: copy.priceOnRequest),
          style: const TextStyle(
              fontSize: 21,
              color: GvColors.accentCyan,
              fontWeight: FontWeight.w800)),
      if (product.unit != null)
        Text('${copy.per} ${product.unit}',
            style: const TextStyle(color: GvColors.textMuted)),
      const SizedBox(height: 8),
      if (enquiry || product.indicativePrice)
        Text(journeyText(
            context,
            'Precio orientativo. Confirmaremos el alcance y el presupuesto antes de contratar.',
            'Indicative price. Scope and quote will be confirmed before you commit.',
            pt: 'Preço indicativo. O âmbito e o orçamento serão confirmados antes da contratação.')),
      if (product.category == 'subscription')
        Text(journeyText(
            context,
            'Monitorización recurrente: instalación, frecuencia y cuota se acordarán en el presupuesto.',
            'Recurring monitoring: installation, frequency and fees will be agreed in the quote.',
            pt: 'Monitorização recorrente: instalação, frequência e mensalidade serão acordadas no orçamento.')),
      const SizedBox(height: 18),
      Text(product.localizedDescription(language),
          style: const TextStyle(color: GvColors.textSecondary, height: 1.5)),
      const SizedBox(height: 20),
      if (product.localizedDeliverables(language).isNotEmpty) ...[
        Text(copy.includes,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
        const SizedBox(height: 8),
        ...product.localizedDeliverables(language).map((item) => Padding(
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
      if (product.category == 'equipment' ||
          product.category == 'hardware') ...[
        const SizedBox(height: 18),
        OutlinedButton.icon(
          onPressed: () => context.go('/guides'),
          icon: const Icon(Icons.menu_book_outlined),
          label: Text(copy.guide),
        ),
      ],
      const SizedBox(height: 28),
      FilledButton.icon(
          onPressed: () {
            if (enquiry) {
              context.push(Uri(path: '/work/new', queryParameters: {
                if (assetId != null) 'asset_id': assetId!,
                'description': product.localizedName(language),
                if (product.category == 'subscription') 'type': 'deviceInstall',
              }).toString());
            } else {
              ref.read(cartProvider.notifier).add(product);
              context.push('/services/cart');
            }
          },
          icon: Icon(
              enquiry ? Icons.request_quote_outlined : Icons.add_shopping_cart),
          label: Text(enquiry
              ? journeyText(context, 'Solicitar presupuesto', 'Request a quote',
                  pt: 'Pedir orçamento')
              : copy.addToCart)),
    ]);
  }
}
