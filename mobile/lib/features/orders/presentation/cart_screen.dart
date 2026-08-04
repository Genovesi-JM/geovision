import 'package:flutter/material.dart';
import '../../../l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../authentication/presentation/auth_controller.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import 'cart_controller.dart';

class CartScreen extends ConsumerStatefulWidget {
  const CartScreen({super.key});
  @override
  ConsumerState<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends ConsumerState<CartScreen> {
  String payment = 'iban_angola';
  bool checkingOut = false;
  final addressController =
      TextEditingController(text: 'Fazenda Boa Vista, Viana, Luanda');

  @override
  void dispose() {
    addressController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lines = ref.watch(cartProvider);
    final currency = ref.watch(storeCurrencyProvider);
    final l10n = AppLocalizations.of(context);
    final sync = ref.watch(cartSyncProvider);
    final paymentOptions = currency == StoreCurrency.akz
        ? const {
            'iban_angola': 'Transferência bancária / IBAN Angola',
            'multicaixa_express': 'Multicaixa Express',
          }
        : const {
            'visa_mastercard': 'Visa / Mastercard',
            'iban_international': 'IBAN internacional',
            'paypal': 'PayPal',
          };
    if (!paymentOptions.containsKey(payment)) {
      payment = paymentOptions.keys.first;
    }
    int totalFor(StoreCurrency target) => lines.fold(
        0,
        (sum, line) =>
            sum +
            StoreMoney.productCents(line.product, target) * line.quantity);
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
            if (sync.isLoading) const LinearProgressIndicator(minHeight: 2),
            if (sync.hasError)
              Container(
                margin: const EdgeInsets.only(bottom: GvSpacing.sm),
                padding: const EdgeInsets.all(GvSpacing.sm),
                decoration: BoxDecoration(
                  color: GvColors.high.withValues(alpha: .12),
                  borderRadius: BorderRadius.circular(GvSpacing.radiusMd),
                ),
                child: const Row(children: [
                  Icon(Icons.cloud_off, color: GvColors.high, size: 18),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'O carrinho ainda não foi sincronizado. Verifique a ligação antes de finalizar.',
                      style: TextStyle(fontSize: 12),
                    ),
                  ),
                ]),
              ),
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
                        Text(StoreMoney.formatProduct(line.product, currency),
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
            GvCard(
                child: TextField(
              controller: addressController,
              minLines: 2,
              maxLines: 3,
              textInputAction: TextInputAction.done,
              decoration: InputDecoration(
                labelText: l10n.deliveryAddress,
                helperText: l10n.deliveryEstimate,
                prefixIcon: const Icon(Icons.location_on_outlined,
                    color: GvColors.accentCyan),
              ),
            )),
            const SizedBox(height: 12),
            const Text('Pagamento',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            DropdownButtonFormField<String>(
              initialValue: payment,
              decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.payments_outlined)),
              items: paymentOptions.entries
                  .map((option) => DropdownMenuItem(
                      value: option.key, child: Text(option.value)))
                  .toList(),
              onChanged: (value) => setState(() => payment = value!),
            ),
            const Divider(),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              const Text('Total',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              Text(StoreMoney.formatCents(totalFor(currency), currency),
                  style: const TextStyle(
                      fontSize: 18,
                      color: GvColors.accentCyan,
                      fontWeight: FontWeight.w800))
            ]),
            const SizedBox(height: 6),
            Align(
              alignment: Alignment.centerRight,
              child: Text(
                StoreCurrency.values
                    .map((target) =>
                        StoreMoney.formatCents(totalFor(target), target))
                    .join('  ·  '),
                style: const TextStyle(color: GvColors.textMuted, fontSize: 11),
              ),
            ),
            const SizedBox(height: 18),
            FilledButton(
                onPressed: checkingOut ||
                        sync.isLoading ||
                        sync.hasError ||
                        addressController.text.trim().isEmpty
                    ? null
                    : () => _checkout(currency),
                child: Text(checkingOut
                    ? 'A processar…'
                    : ref.read(ordersRepositoryProvider).isDemo
                        ? 'Finalizar pedido (demo)'
                        : 'Confirmar encomenda')),
          ],
        ]));
  }

  Future<void> _checkout(StoreCurrency currency) async {
    final session = ref.read(authControllerProvider);
    final profile = session.profile;
    setState(() => checkingOut = true);
    try {
      final result = await ref.read(ordersRepositoryProvider).checkout(
            currency: switch (currency) {
              StoreCurrency.akz => 'AOA',
              StoreCurrency.eur => 'EUR',
              StoreCurrency.usd => 'USD',
            },
            paymentMethod: payment,
            name: profile?.displayName ?? 'Cliente GeoVision',
            email: profile?.email ?? 'demo@geovisionops.com',
            phone: profile?.phone,
            company: profile?.organisation,
            address: addressController.text.trim(),
          );
      if (!mounted) return;
      if (result.success) {
        ref.read(cartProvider.notifier).clear();
        ref.invalidate(ordersProvider);
      }
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          icon: Icon(result.success ? Icons.check_circle : Icons.error_outline,
              color: result.success ? GvColors.accentGreen : GvColors.critical),
          title:
              Text(result.success ? 'Encomenda criada' : 'Falha no checkout'),
          content: Text(result.success
              ? 'Referência ${result.orderNumber ?? result.orderId ?? ''}. '
                  '${result.paymentRequired ? 'Siga as instruções do método de pagamento selecionado.' : 'Nenhum pagamento real foi efetuado em modo demo.'}'
              : result.error ?? 'Não foi possível criar a encomenda.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('OK'),
            ),
          ],
        ),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Checkout não concluído: $error')),
      );
    } finally {
      if (mounted) setState(() => checkingOut = false);
    }
  }
}
