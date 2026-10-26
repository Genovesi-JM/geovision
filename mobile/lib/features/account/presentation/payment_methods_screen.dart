import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../app/providers.dart';
import '../../../core/localization/journey_copy.dart';
import '../../orders/data/payment_availability.dart';

class PaymentMethodsScreen extends ConsumerWidget {
  const PaymentMethodsScreen({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        appBar: AppBar(
            title: Text(journeyText(
                context, 'Métodos de pago', 'Payment methods',
                pt: 'Métodos de pagamento'))),
        body: ref.watch(availablePaymentsProvider).when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (_, __) => Center(
                  child: TextButton(
                      onPressed: () =>
                          ref.invalidate(availablePaymentsProvider),
                      child: Text(journeyText(
                          context,
                          'No se pudo comprobar. Reintentar',
                          'Could not check availability. Retry',
                          pt: 'Não foi possível verificar a disponibilidade. Tentar novamente')))),
              data: (methods) =>
                  ListView(padding: const EdgeInsets.all(24), children: [
                if (ref.watch(appConfigProvider).demoMode)
                  Text(journeyText(context, 'Demostración: no se cobran pagos.',
                      'Demo: no payments are collected.',
                      pt: 'Demonstração: não são cobrados pagamentos.')),
                Text(methods.isEmpty
                    ? journeyText(
                        context,
                        'Los pagos en la app todavía no están disponibles. Puedes solicitar un servicio sin pagar ahora.',
                        'In-app payments are not available yet. You can request a service without paying now.',
                        pt:
                            'Os pagamentos na app ainda não estão disponíveis. Pode pedir um serviço sem pagar agora.')
                    : journeyText(
                        context,
                        'Disponibles al confirmar el pedido, según la moneda:',
                        'Available at checkout, depending on currency:',
                        pt: 'Disponíveis ao confirmar a encomenda, conforme a moeda:')),
                for (final method in methods)
                  ListTile(title: Text(paymentLabels[method] ?? method)),
                TextButton(
                    onPressed: () => context.go('/work/new'),
                    child: Text(journeyText(
                        context, 'Solicitar servicio', 'Request service',
                        pt: 'Pedir serviço'))),
              ]),
            ),
      );
}
