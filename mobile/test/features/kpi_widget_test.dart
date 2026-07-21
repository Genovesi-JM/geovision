import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/core/widgets/kpi_card.dart';
import 'package:geovision/core/widgets/severity_chip.dart';

void main() {
  testWidgets('KpiCard renders label, value and unit', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: KpiCard(
            label: 'Average NDVI',
            value: '0.72',
            unit: '',
            spark: [0.6, 0.7, 0.72]),
      ),
    ));
    expect(find.text('Average NDVI'), findsOneWidget);
    expect(find.text('0.72'), findsOneWidget);
  });

  testWidgets('SeverityChip maps critical severity', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: SeverityChip(severityFromString('critical'))),
    ));
    expect(find.text('CRITICAL'), findsOneWidget);
  });
}
