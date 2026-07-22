import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';

class PaymentMethodsScreen extends StatelessWidget {
  const PaymentMethodsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final copy = _PaymentCopy(Localizations.localeOf(context).languageCode);
    return Scaffold(
      appBar: AppBar(title: Text(copy.title)),
      body: ListView(padding: const EdgeInsets.all(GvSpacing.lg), children: [
        GvCard(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(copy.accepted,
              style:
                  const TextStyle(fontSize: 18, fontWeight: FontWeight.w900)),
          const SizedBox(height: 5),
          Text(copy.subtitle,
              style:
                  const TextStyle(color: GvColors.textSecondary, fontSize: 12)),
          const SizedBox(height: 14),
          const Row(children: [
            _Logo('assets/images/payments/payment-multicaixa.png'),
            _Logo('assets/images/payments/payment-visa.png'),
            _Logo('assets/images/payments/payment-mastercard.png'),
          ]),
        ])),
        const SizedBox(height: GvSpacing.md),
        _Method(
            icon: Icons.qr_code_2,
            title: 'Multicaixa Express',
            currencies: 'AKZ / AOA',
            body: copy.multicaixa),
        _Method(
            icon: Icons.account_balance_outlined,
            title: 'IBAN Angola',
            currencies: 'AKZ / AOA',
            body: copy.ibanAngola),
        _Method(
            icon: Icons.credit_card,
            title: 'Visa / Mastercard',
            currencies: 'EUR · USD',
            body: copy.cards),
        _Method(
            icon: Icons.language,
            title: 'IBAN Internacional',
            currencies: 'EUR · USD',
            body: copy.ibanInternational),
        _Method(
            icon: Icons.paypal,
            title: 'PayPal',
            currencies: 'EUR · USD',
            body: copy.paypal),
        const SizedBox(height: GvSpacing.sm),
        Container(
          padding: const EdgeInsets.all(GvSpacing.md),
          decoration: BoxDecoration(
              color: GvColors.medium.withValues(alpha: .11),
              borderRadius: BorderRadius.circular(14)),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.info_outline, color: GvColors.medium),
            const SizedBox(width: 10),
            Expanded(
                child: Text(copy.notice,
                    style: const TextStyle(fontSize: 12, height: 1.35))),
          ]),
        ),
        const SizedBox(height: GvSpacing.lg),
        FilledButton.icon(
            onPressed: () => context.go('/orders'),
            icon: const Icon(Icons.storefront),
            label: Text(copy.openStore)),
      ]),
    );
  }
}

class _Logo extends StatelessWidget {
  const _Logo(this.asset);
  final String asset;
  @override
  Widget build(BuildContext context) => Expanded(
        child: Container(
          height: 42,
          margin: const EdgeInsets.only(right: 8),
          padding: const EdgeInsets.all(7),
          decoration: BoxDecoration(
              color: Colors.white, borderRadius: BorderRadius.circular(9)),
          child: Image.asset(asset, fit: BoxFit.contain),
        ),
      );
}

class _Method extends StatelessWidget {
  const _Method(
      {required this.icon,
      required this.title,
      required this.currencies,
      required this.body});
  final IconData icon;
  final String title;
  final String currencies;
  final String body;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: GvSpacing.sm),
        child: GvCard(
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          CircleAvatar(
              backgroundColor: GvColors.accentGreen.withValues(alpha: .13),
              child: Icon(icon, color: GvColors.accentGreen)),
          const SizedBox(width: 12),
          Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                Row(children: [
                  Expanded(
                      child: Text(title,
                          style: const TextStyle(fontWeight: FontWeight.w800))),
                  Text(currencies,
                      style: const TextStyle(
                          color: GvColors.accentCyan,
                          fontSize: 10,
                          fontWeight: FontWeight.w800)),
                ]),
                const SizedBox(height: 4),
                Text(body,
                    style: const TextStyle(
                        color: GvColors.textSecondary, fontSize: 12)),
              ])),
        ])),
      );
}

class _PaymentCopy {
  const _PaymentCopy(this.language);
  final String language;
  String t(String pt, String en, String es, String fr) =>
      switch (language) { 'pt' => pt, 'es' => es, 'fr' => fr, _ => en };
  String get title => t('Formas de pagamento', 'Payment methods',
      'Métodos de pago', 'Moyens de paiement');
  String get accepted => t('Pagamentos aceites', 'Accepted payments',
      'Pagos aceptados', 'Paiements acceptés');
  String get subtitle => t(
      'A disponibilidade final depende da moeda, país e configuração comercial.',
      'Final availability depends on currency, country and commercial configuration.',
      'La disponibilidad final depende de la moneda, el país y la configuración comercial.',
      'La disponibilité finale dépend de la devise, du pays et de la configuration commerciale.');
  String get multicaixa => t(
      'Pagamento por QR code ou referência.',
      'Pay by QR code or reference.',
      'Pago por QR o referencia.',
      'Paiement par QR code ou référence.');
  String get ibanAngola => t(
      'Transferência bancária local em kwanzas.',
      'Local bank transfer in kwanza.',
      'Transferencia bancaria local en kwanzas.',
      'Virement bancaire local en kwanzas.');
  String get cards => t(
      'Cartão internacional processado por fornecedor seguro.',
      'International card processed by a secure provider.',
      'Tarjeta internacional procesada por un proveedor seguro.',
      'Carte internationale traitée par un prestataire sécurisé.');
  String get ibanInternational => t(
      'Transferência SWIFT/SEPA em euros ou dólares.',
      'SWIFT/SEPA transfer in euros or dollars.',
      'Transferencia SWIFT/SEPA en euros o dólares.',
      'Virement SWIFT/SEPA en euros ou dollars.');
  String get paypal => t(
      'Pagamento online seguro via PayPal.',
      'Secure online payment through PayPal.',
      'Pago seguro en línea mediante PayPal.',
      'Paiement en ligne sécurisé via PayPal.');
  String get notice => t(
      'Nenhum pagamento é executado nesta página. O checkout confirma os métodos realmente disponíveis e apresenta instruções do backend. Nunca envie comprovativos fora dos canais oficiais.',
      'No payment is executed on this page. Checkout confirms the methods actually available and displays backend instructions. Never send receipts outside official channels.',
      'No se ejecuta ningún pago en esta página. El checkout confirma los métodos disponibles y muestra las instrucciones del servidor.',
      'Aucun paiement n’est exécuté ici. Le checkout confirme les moyens disponibles et affiche les instructions du serveur.');
  String get openStore =>
      t('Abrir loja', 'Open store', 'Abrir tienda', 'Ouvrir la boutique');
}
