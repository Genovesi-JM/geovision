import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../domain/currency.dart';
import 'cart_controller.dart';

class CartScreen extends ConsumerStatefulWidget {
  const CartScreen({super.key});
  @override
  ConsumerState<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends ConsumerState<CartScreen> {
  String payment = 'bank';
  @override
  Widget build(BuildContext context) {
    final lines = ref.watch(cartProvider);
    final total = ref.watch(cartTotalProvider);
    final currency = ref.watch(storeCurrencyProvider);
    return Scaffold(
        appBar: AppBar(title: const Text('Carrinho')),
        body: ListView(padding: const EdgeInsets.all(GvSpacing.lg), children: [
          if (lines.isEmpty)
            const Padding(
                padding: EdgeInsets.only(top: 100),
                child: Column(children: [
                  Icon(Icons.shopping_cart_outlined,
                      size: 64, color: GvColors.textMuted),
                  SizedBox(height: 12),
                  Text('O seu carrinho está vazio.')
                ]))
          else ...[
            ...lines.map((line) => Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: GvCard(
                    child: Row(children: [
                  const Icon(Icons.inventory_2_outlined,
                      color: GvColors.accentGreen),
                  const SizedBox(width: 12),
                  Expanded(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        Text(line.product.name,
                            style:
                                const TextStyle(fontWeight: FontWeight.w700)),
                        Text(
                            StoreMoney.formatUsdCents(
                                line.product.priceCents, currency),
                            style: const TextStyle(color: GvColors.textMuted))
                      ])),
                  IconButton(
                      onPressed: () => ref
                          .read(cartProvider.notifier)
                          .changeQuantity(line.product.id, line.quantity - 1),
                      icon: const Icon(Icons.remove)),
                  Text('${line.quantity}',
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  IconButton(
                      onPressed: () => ref
                          .read(cartProvider.notifier)
                          .changeQuantity(line.product.id, line.quantity + 1),
                      icon: const Icon(Icons.add)),
                ])))),
            const SizedBox(height: 12),
            const Text('Entrega',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            const GvCard(
                child: ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(Icons.location_on_outlined,
                        color: GvColors.accentCyan),
                    title: Text('Fazenda Boa Vista'),
                    subtitle: Text('Viana, Luanda · Entrega estimada 3–5 dias'),
                    trailing: Icon(Icons.edit_outlined))),
            const SizedBox(height: 12),
            const Text('Pagamento',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            DropdownButtonFormField<String>(
              initialValue: payment,
              decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.payments_outlined)),
              items: const [
                DropdownMenuItem(
                    value: 'bank',
                    child: Text('Transferência bancária / IBAN')),
                DropdownMenuItem(
                    value: 'card', child: Text('Cartão (integração futura)')),
                DropdownMenuItem(
                    value: 'multicaixa',
                    child: Text('Referência / Multicaixa')),
              ],
              onChanged: (value) => setState(() => payment = value!),
            ),
            const Divider(),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              const Text('Total',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              Text(StoreMoney.formatUsdCents(total, currency),
                  style: const TextStyle(
                      fontSize: 18,
                      color: GvColors.accentCyan,
                      fontWeight: FontWeight.w800))
            ]),
            const SizedBox(height: 6),
            Align(
              alignment: Alignment.centerRight,
              child: Text(
                StoreMoney.allPrices(total).join('  ·  '),
                style: const TextStyle(color: GvColors.textMuted, fontSize: 11),
              ),
            ),
            const SizedBox(height: 18),
            FilledButton(
                onPressed: () => showDialog<void>(
                    context: context,
                    builder: (_) => AlertDialog(
                            title: const Text('Pedido preparado'),
                            content: const Text(
                                'O fluxo está em modo de demonstração. Nenhum pagamento real foi efetuado.'),
                            actions: [
                              TextButton(
                                  onPressed: () => Navigator.pop(context),
                                  child: const Text('OK'))
                            ])),
                child: const Text('Finalizar pedido (demo)')),
          ],
        ]));
  }
}
