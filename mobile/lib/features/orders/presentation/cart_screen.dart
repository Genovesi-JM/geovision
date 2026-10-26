import 'package:flutter/material.dart';
import '../../../l10n/app_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/localization/journey_copy.dart';
import '../data/payment_availability.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../authentication/presentation/auth_controller.dart';
import '../data/orders_repository.dart';
import '../domain/currency.dart';
import 'cart_controller.dart';
import 'store_copy.dart';

class CartScreen extends ConsumerStatefulWidget {
  const CartScreen({super.key});
  @override
  ConsumerState<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends ConsumerState<CartScreen> {
  String payment = 'visa_mastercard';
  bool checkingOut = false;
  final addressController = TextEditingController();

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
    final copy = StoreCopy.of(context);
    final language = Localizations.localeOf(context).languageCode;
    final sync = ref.watch(cartSyncProvider);
    final demo = ref.watch(ordersRepositoryProvider).isDemo;
    final remote = ref.watch(checkoutCartProvider);
    final confirmedTotal = remote.valueOrNull?.total;
    final totalReady = demo ||
        (!remote.isLoading && !remote.hasError && confirmedTotal != null);
    final availability = ref.watch(availablePaymentsProvider);
    final available = availability.valueOrNull ?? const <String>[];
    final paymentOptions = Map<String, String>.fromEntries(paymentLabels.entries
        .where((e) =>
            available.contains(e.key) &&
            (currency == StoreCurrency.akz
                ? const ['iban_angola', 'multicaixa_express'].contains(e.key)
                : const ['visa_mastercard', 'iban_international', 'paypal']
                    .contains(e.key))));
    if (!paymentOptions.containsKey(payment)) {
      payment = paymentOptions.keys.firstOrNull ?? '';
    }
    int? totalFor(StoreCurrency target) {
      var total = 0;
      for (final line in lines) {
        final price = StoreMoney.productCents(line.product, target);
        if (price == null) return null;
        total += price * line.quantity;
      }
      return total;
    }

    final displayTotal =
        demo ? totalFor(currency) : confirmedTotal ?? totalFor(currency);
    return Scaffold(
        appBar: AppBar(title: Text(copy.cart)),
        body: ListView(padding: const EdgeInsets.all(GvSpacing.lg), children: [
          if (lines.isEmpty)
            Padding(
                padding: const EdgeInsets.only(top: 100),
                child: Column(children: [
                  const Icon(Icons.shopping_cart_outlined,
                      size: 64, color: GvColors.textMuted),
                  const SizedBox(height: 12),
                  Text(copy.emptyCart)
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
                child: Row(children: [
                  const Icon(Icons.cloud_off, color: GvColors.high, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      copy.syncError,
                      style: const TextStyle(fontSize: 12),
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
                        Text(line.product.localizedName(language),
                            style:
                                const TextStyle(fontWeight: FontWeight.w700)),
                        Text(
                            StoreMoney.formatProduct(line.product, currency,
                                unavailable: copy.priceOnRequest),
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
            Text(copy.delivery,
                style:
                    const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            GvCard(
                child: TextField(
              controller: addressController,
              onChanged: (_) => setState(() {}),
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
            Text(copy.payment,
                style:
                    const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            if (availability.isLoading) const LinearProgressIndicator(),
            if (availability.hasError)
              TextButton(
                  onPressed: () => ref.invalidate(availablePaymentsProvider),
                  child: Text(journeyText(
                      context,
                      'No se pudo comprobar los pagos. Reintentar',
                      'Could not check payments. Retry',
                      pt: 'Não foi possível verificar os pagamentos. Tentar novamente'))),
            if (!availability.isLoading &&
                !availability.hasError &&
                paymentOptions.isEmpty)
              Text(journeyText(
                  context,
                  'El pago en la app aún no está disponible. No se creará un pedido ni se cobrará ningún importe.',
                  'In-app payment is not available yet. No order or charge will be created.',
                  pt: 'O pagamento na app ainda não está disponível. Não será criada uma encomenda nem cobrado qualquer valor.')),
            if (paymentOptions.isNotEmpty)
              DropdownButtonFormField<String>(
                key: ValueKey(paymentOptions.keys.join(',')),
                initialValue: payment,
                decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.payments_outlined)),
                items: paymentOptions.entries
                    .map((option) => DropdownMenuItem(
                        value: option.key, child: Text(option.value)))
                    .toList(),
                onChanged: (value) => setState(() => payment = value!),
              ),
            if (!demo && remote.isLoading) const LinearProgressIndicator(),
            if (!demo && remote.hasError)
              TextButton(
                  onPressed: () => ref.invalidate(checkoutCartProvider),
                  child: Text(journeyText(
                      context,
                      'No se pudo confirmar el total. Reintentar',
                      'Could not confirm the total. Retry',
                      pt: 'Não foi possível confirmar o total. Tentar novamente'))),
            if (!demo && confirmedTotal == null)
              Text(journeyText(
                  context,
                  'Importe provisional: pendiente de impuestos y entrega.',
                  'Provisional amount: tax and delivery have not been confirmed.',
                  pt: 'Valor provisório: impostos e entrega por confirmar.')),
            const Divider(),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text(copy.total,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w800)),
              Text(
                  displayTotal == null
                      ? copy.priceOnRequest
                      : StoreMoney.formatCents(displayTotal, currency),
                  style: const TextStyle(
                      fontSize: 18,
                      color: GvColors.accentCyan,
                      fontWeight: FontWeight.w800))
            ]),
            const SizedBox(height: 6),
            const SizedBox(height: 18),
            FilledButton(
                onPressed: displayTotal == null ||
                        !totalReady ||
                        paymentOptions.isEmpty ||
                        lines.any((line) => line.product.requiresEnquiry) ||
                        checkingOut ||
                        sync.isLoading ||
                        sync.hasError ||
                        addressController.text.trim().isEmpty
                    ? null
                    : () => _checkout(currency),
                child: Text(checkingOut
                    ? copy.processing
                    : ref.read(ordersRepositoryProvider).isDemo
                        ? copy.finishDemo
                        : copy.confirmOrder)),
          ],
        ]));
  }

  Future<void> _checkout(StoreCurrency currency) async {
    final copy = StoreCopy.of(context);
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
          title: Text(result.success ? copy.orderCreated : copy.checkoutFailed),
          content: SingleChildScrollView(
              child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Text(result.success
                    ? '${journeyText(context, 'Referencia', 'Reference', pt: 'Referência')} ${result.orderNumber ?? result.orderId ?? ''}. '
                        '${result.paymentRequired ? copy.paymentInstructions : copy.demoNoPayment}'
                    : result.error ?? copy.couldNotCreate),
                if (result.success &&
                    result.paymentData['transfer_details'] is Map)
                  for (final entry
                      in (result.paymentData['transfer_details'] as Map)
                          .entries)
                    if (const [
                      'iban',
                      'bic',
                      'bank_name',
                      'beneficiary',
                      'reference',
                      'amount',
                      'currency'
                    ].contains(entry.key))
                      SelectableText('${entry.key}: ${entry.value}'),
              ])),
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
        SnackBar(content: Text(copy.checkoutError(error))),
      );
    } finally {
      if (mounted) setState(() => checkingOut = false);
    }
  }
}
