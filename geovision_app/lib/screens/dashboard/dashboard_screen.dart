import 'package:flutter/material.dart';

import '../../services/api_client.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _loading = true;
  String? _error;

  int? _servicesActive;
  int? _hardwareActive;
  int? _reportsReady;
  int? _alertsOpen;

  @override
  void initState() {
    super.initState();
    _loadKpis();
  }

  Future<void> _loadKpis() async {
    try {
      final data = await ApiClient.instance.getJson('/kpi/summary');
      final items = (data['items'] as List<dynamic>? ?? []);

      int? services;
      int? hardware;
      int? reports;
      int? alerts;

      for (final raw in items) {
        if (raw is! Map<String, dynamic>) continue;
        final id = raw['id'] as String?;
        final value = raw['value'];
        if (id == null || value is! num) continue;
        switch (id) {
          case 'services_active':
            services = value.toInt();
            break;
          case 'hardware_active':
            hardware = value.toInt();
            break;
          case 'reports_ready':
            reports = value.toInt();
            break;
          case 'alerts_open':
            alerts = value.toInt();
            break;
        }
      }

      if (!mounted) return;
      setState(() {
        _servicesActive = services;
        _hardwareActive = hardware;
        _reportsReady = reports;
        _alertsOpen = alerts;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Conta GeoVision',
              style:
                  textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 4),
            Text(
              'Visão geral de serviços, hardware, relatórios e alertas.',
              style: textTheme.bodySmall,
            ),
            const SizedBox(height: 16),

            if (_loading) ...[
              const LinearProgressIndicator(minHeight: 2),
              const SizedBox(height: 12),
            ] else if (_error != null) ...[
              Text(
                'Erro ao carregar KPIs: $_error',
                style: textTheme.bodySmall?.copyWith(color: Colors.redAccent),
              ),
              const SizedBox(height: 12),
            ],

            // KPI row
            Row(
              children: [
                Expanded(
                  child: _KpiCard(
                    label: 'Serviços ativos',
                    value: _valueText(_servicesActive),
                  ),
                ),
                SizedBox(width: 8),
                Expanded(
                  child: _KpiCard(
                    label: 'Hardware instalado',
                    value: _valueText(_hardwareActive),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: _KpiCard(
                    label: 'Relatórios',
                    value: _valueText(_reportsReady),
                  ),
                ),
                SizedBox(width: 8),
                Expanded(
                  child: _KpiCard(
                    label: 'Alertas',
                    value: _valueText(_alertsOpen),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 20),

            const _SectionCard(
              title: 'Operações em curso',
              badge: '0 ativos',
              child: _PlaceholderTable(
                columns: ['Tipo', 'Local', 'Área', 'Estado'],
                emptyText:
                    'Ainda não existem serviços registados. Assim que existir backend, aparecem aqui.',
              ),
            ),

            const SizedBox(height: 12),

            const _SectionCard(
              title: 'Alertas & atenção',
              badge: 'Ao vivo',
              child: Text(
                'Sem alertas críticos no momento.',
              ),
            ),

            const SizedBox(height: 12),

            const _SectionCard(
              title: 'Hardware instalado',
              child: _PlaceholderTable(
                columns: ['Equipamento', 'Local', 'Estado'],
                emptyText: 'Nenhum hardware registado na sua conta (ainda).',
              ),
            ),

            const SizedBox(height: 12),

            const _SectionCard(
              title: 'Relatórios',
              child: _PlaceholderTable(
                columns: ['Relatório', 'Serviço', 'Entrega', 'Estado'],
                emptyText:
                    'Ainda não existem relatórios prontos. Quando finalizarmos um serviço, aparece aqui.',
              ),
            ),

            const SizedBox(height: 12),

            const _SectionCard(
              title: 'Mapa / Layers',
              badge: 'Em breve',
              child: Text(
                'Visualização de camadas, últimos voos e alertas geográficos (placeholder).',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _valueText(int? value) => value == null ? '—' : value.toString();

class _KpiCard extends StatelessWidget {
  const _KpiCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white10),
        color: Colors.white.withOpacity(0.02),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: textTheme.bodySmall?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 6),
          Text(
            value,
            style:
                textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }
}

class _SectionCard extends StatelessWidget {
  const _SectionCard({
    required this.title,
    required this.child,
    this.badge,
  });

  final String title;
  final String? badge;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white10),
        color: Colors.white.withOpacity(0.02),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                title,
                style: textTheme.titleMedium
                    ?.copyWith(fontWeight: FontWeight.w600),
              ),
              if (badge != null)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(999),
                    color: Colors.white10,
                  ),
                  child: Text(
                    badge!,
                    style: textTheme.labelSmall,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}

class _PlaceholderTable extends StatelessWidget {
  const _PlaceholderTable({
    required this.columns,
    required this.emptyText,
  });

  final List<String> columns;
  final String emptyText;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: [
              for (final c in columns)
                DataColumn(
                  label: Text(
                    c,
                    style: textTheme.labelSmall,
                  ),
                ),
            ],
            rows: const [],
          ),
        ),
        const SizedBox(height: 4),
        Text(
          emptyText,
          style: textTheme.bodySmall?.copyWith(color: Colors.white70),
        ),
      ],
    );
  }
}
