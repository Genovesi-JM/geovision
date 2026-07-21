import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';
import 'gv_card.dart';

enum KpiStatus { ok, warning, critical }

enum KpiTrend { up, down, stable }

KpiStatus kpiStatusFromString(String? v) {
  switch (v) {
    case 'critical':
      return KpiStatus.critical;
    case 'warning':
      return KpiStatus.warning;
    default:
      return KpiStatus.ok;
  }
}

/// Compact KPI tile with value, unit, status colour and an optional sparkline
/// — the data-visualisation style used across GeoVision dashboards.
class KpiCard extends StatelessWidget {
  const KpiCard({
    super.key,
    required this.label,
    required this.value,
    this.unit,
    this.status = KpiStatus.ok,
    this.trend = KpiTrend.stable,
    this.spark = const [],
    this.onTap,
  });

  final String label;
  final String value;
  final String? unit;
  final KpiStatus status;
  final KpiTrend trend;
  final List<double> spark;
  final VoidCallback? onTap;

  Color get _statusColor {
    switch (status) {
      case KpiStatus.critical:
        return GvColors.critical;
      case KpiStatus.warning:
        return GvColors.medium;
      case KpiStatus.ok:
        return GvColors.accentGreen;
    }
  }

  IconData get _trendIcon {
    switch (trend) {
      case KpiTrend.up:
        return Icons.trending_up;
      case KpiTrend.down:
        return Icons.trending_down;
      case KpiTrend.stable:
        return Icons.trending_flat;
    }
  }

  @override
  Widget build(BuildContext context) {
    return GvCard(
      onTap: onTap,
      padding: const EdgeInsets.all(GvSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: GvColors.textSecondary, fontSize: 12)),
              ),
              Icon(_trendIcon, size: 14, color: _statusColor),
            ],
          ),
          const SizedBox(height: GvSpacing.sm),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(value,
                  style: const TextStyle(
                      color: GvColors.textPrimary,
                      fontSize: 22,
                      fontWeight: FontWeight.w800)),
              if (unit != null) ...[
                const SizedBox(width: 4),
                Text(unit!,
                    style: const TextStyle(
                        color: GvColors.textMuted, fontSize: 12)),
              ],
            ],
          ),
          if (spark.length > 1) ...[
            const SizedBox(height: GvSpacing.sm),
            SizedBox(height: 28, child: _Spark(spark, _statusColor)),
          ],
        ],
      ),
    );
  }
}

class _Spark extends StatelessWidget {
  const _Spark(this.data, this.color);
  final List<double> data;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineTouchData: const LineTouchData(enabled: false),
        minY: data.reduce((a, b) => a < b ? a : b),
        maxY: data.reduce((a, b) => a > b ? a : b),
        lineBarsData: [
          LineChartBarData(
            spots: [
              for (var i = 0; i < data.length; i++)
                FlSpot(i.toDouble(), data[i]),
            ],
            isCurved: true,
            color: color,
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData:
                BarAreaData(show: true, color: color.withValues(alpha: 0.12)),
          ),
        ],
      ),
    );
  }
}
