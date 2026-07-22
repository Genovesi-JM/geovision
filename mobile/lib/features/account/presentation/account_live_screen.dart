import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/gv_card.dart';
import '../../orders/domain/currency.dart';
import '../data/account_overview_repository.dart';
import '../domain/account_overview.dart';

class AccountLiveScreen extends ConsumerStatefulWidget {
  const AccountLiveScreen({super.key});

  @override
  ConsumerState<AccountLiveScreen> createState() => _AccountLiveScreenState();
}

class _AccountLiveScreenState extends ConsumerState<AccountLiveScreen> {
  Timer? _refresh;

  @override
  void initState() {
    super.initState();
    _refresh = Timer.periodic(const Duration(seconds: 10), (_) {
      if (mounted) ref.invalidate(accountOverviewProvider);
    });
  }

  @override
  void dispose() {
    _refresh?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final language = Localizations.localeOf(context).languageCode;
    final overview = ref.watch(accountOverviewProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(_t(language, 'A minha conta', 'My account', 'Mi cuenta',
            'Mon compte')),
        actions: [
          IconButton(
            tooltip: _t(
                language, 'Atualizar', 'Refresh', 'Actualizar', 'Actualiser'),
            onPressed: () => ref.invalidate(accountOverviewProvider),
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: overview.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(GvSpacing.xl),
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              const Icon(Icons.cloud_off, color: GvColors.high, size: 38),
              const SizedBox(height: 12),
              Text(_t(
                  language,
                  'Não foi possível atualizar a conta.',
                  'Could not refresh the account.',
                  'No se pudo actualizar la cuenta.',
                  'Impossible d’actualiser le compte.')),
              TextButton(
                  onPressed: () => ref.invalidate(accountOverviewProvider),
                  child: Text(_t(language, 'Tentar novamente', 'Try again',
                      'Reintentar', 'Réessayer'))),
            ]),
          ),
        ),
        data: (data) => _AccountBody(data: data, language: language),
      ),
    );
  }
}

class _AccountBody extends StatelessWidget {
  const _AccountBody({required this.data, required this.language});
  final AccountOverview data;
  final String language;

  @override
  Widget build(BuildContext context) => RefreshIndicator(
        onRefresh: () async => ProviderScope.containerOf(context)
            .invalidate(accountOverviewProvider),
        child: ListView(
          padding: const EdgeInsets.all(GvSpacing.lg),
          children: [
            GvCard(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Row(children: [
                    const Icon(Icons.podcasts,
                        color: GvColors.accentGreen, size: 18),
                    const SizedBox(width: 8),
                    Text(
                        _t(
                            language,
                            'Atualização em tempo real',
                            'Live account data',
                            'Datos en tiempo real',
                            'Données en temps réel'),
                        style: const TextStyle(
                            color: GvColors.accentGreen,
                            fontWeight: FontWeight.w700)),
                  ]),
                  const SizedBox(height: 12),
                  Text(data.organisationName,
                      style: const TextStyle(
                          fontSize: 20, fontWeight: FontWeight.w800)),
                  Text('${data.plan} · ${data.status}',
                      style: const TextStyle(color: GvColors.textSecondary)),
                  const SizedBox(height: 8),
                  Text(
                      '${_t(language, 'Atualizado', 'Updated', 'Actualizado', 'Actualisé')}: ${TimeOfDay.fromDateTime(data.lastUpdatedAt.toLocal()).format(context)}',
                      style: const TextStyle(
                          color: GvColors.textMuted, fontSize: 12)),
                ])),
            const SizedBox(height: GvSpacing.md),
            GvCard(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                  Text(
                      _t(language, 'Resumo financeiro', 'Financial summary',
                          'Resumen financiero', 'Résumé financier'),
                      style: const TextStyle(fontWeight: FontWeight.w800)),
                  const SizedBox(height: 12),
                  Text(
                      StoreMoney.formatOrder(
                          data.outstandingCents, data.currency),
                      style: const TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w900,
                          color: GvColors.accentCyan)),
                  Text(
                      _t(language, 'Total pendente', 'Outstanding total',
                          'Total pendiente', 'Total impayé'),
                      style: const TextStyle(color: GvColors.textSecondary)),
                  const Divider(height: 28),
                  Row(children: [
                    Expanded(
                        child: _Metric(
                            label: _t(
                                language,
                                'Pagamentos concluídos',
                                'Payments completed',
                                'Pagos completados',
                                'Paiements terminés'),
                            value: '${data.paidPayments}')),
                    Expanded(
                        child: _Metric(
                            label: _t(
                                language,
                                'Pagamentos pendentes',
                                'Payments pending',
                                'Pagos pendientes',
                                'Paiements en attente'),
                            value: '${data.pendingPayments}'))
                  ]),
                ])),
            const SizedBox(height: GvSpacing.md),
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              childAspectRatio: 1.55,
              mainAxisSpacing: GvSpacing.sm,
              crossAxisSpacing: GvSpacing.sm,
              children: [
                _ActionMetric(
                    icon: Icons.location_on_outlined,
                    value: '${data.sites}',
                    label: _t(language, 'Locais', 'Sites', 'Sitios', 'Sites'),
                    onTap: () => context.go('/sites')),
                _ActionMetric(
                    icon: Icons.local_shipping_outlined,
                    value: '${data.activeOrders}',
                    label: _t(language, 'Pedidos ativos', 'Active orders',
                        'Pedidos activos', 'Commandes actives'),
                    onTap: () => context.go('/orders')),
                _ActionMetric(
                    icon: Icons.work_outline,
                    value: '${data.activeRequests}',
                    label: _t(language, 'Serviços ativos', 'Active services',
                        'Servicios activos', 'Services actifs'),
                    onTap: () => context.go('/work')),
                _ActionMetric(
                    icon: Icons.receipt_long_outlined,
                    value: '${data.orders}',
                    label: _t(language, 'Total de pedidos', 'Total orders',
                        'Total pedidos', 'Total commandes'),
                    onTap: () => context.go('/orders')),
              ],
            ),
            if (data.recentOrders.isNotEmpty) ...[
              const SizedBox(height: GvSpacing.lg),
              Text(
                  _t(
                      language,
                      'Atividade comercial recente',
                      'Recent commercial activity',
                      'Actividad comercial reciente',
                      'Activité commerciale récente'),
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w800)),
              const SizedBox(height: GvSpacing.sm),
              for (final order in data.recentOrders)
                GvCard(
                  onTap: () => context.go('/orders/${order.id}'),
                  child: Row(children: [
                    const Icon(Icons.inventory_2_outlined,
                        color: GvColors.accentCyan),
                    const SizedBox(width: 12),
                    Expanded(
                        child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                          Text(order.number,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700)),
                          Text(order.status,
                              style: const TextStyle(
                                  color: GvColors.textSecondary, fontSize: 12))
                        ])),
                    Text(
                        StoreMoney.formatOrder(
                            order.totalCents, order.currency),
                        style: const TextStyle(fontWeight: FontWeight.w800)),
                  ]),
                ),
            ],
            const SizedBox(height: 40),
          ],
        ),
      );
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value,
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800)),
        Text(label,
            style: const TextStyle(color: GvColors.textSecondary, fontSize: 11))
      ]);
}

class _ActionMetric extends StatelessWidget {
  const _ActionMetric(
      {required this.icon,
      required this.value,
      required this.label,
      required this.onTap});
  final IconData icon;
  final String value;
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => GvCard(
      onTap: onTap,
      child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: GvColors.accentCyan),
            const Spacer(),
            Text(value,
                style:
                    const TextStyle(fontSize: 21, fontWeight: FontWeight.w900)),
            Text(label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: GvColors.textSecondary, fontSize: 11))
          ]));
}

String _t(String language, String pt, String en, String es, String fr) =>
    switch (language) { 'pt' => pt, 'es' => es, 'fr' => fr, _ => en };
