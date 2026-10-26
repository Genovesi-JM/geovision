// Native hand-off smoke test using synthetic PDF bytes; no customer report.
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:geovision/features/reports/data/report_files.dart';

Uint8List syntheticPdf() {
  const content =
      'BT /F1 20 Tf 40 750 Td (GeoVision - synthetic PDF test) Tj ET';
  final objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    '<< /Length ${content.length} >>\nstream\n$content\nendstream',
  ];
  var pdf = '%PDF-1.4\n';
  final offsets = <int>[];
  for (var i = 0; i < objects.length; i++) {
    offsets.add(pdf.length);
    pdf += '${i + 1} 0 obj\n${objects[i]}\nendobj\n';
  }
  final start = pdf.length;
  pdf += 'xref\n0 6\n0000000000 65535 f \n';
  for (final offset in offsets) {
    pdf += '${offset.toString().padLeft(10, '0')} 00000 n \n';
  }
  pdf += 'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n$start\n%%EOF\n';
  return Uint8List.fromList(ascii.encode(pdf));
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('native PDF viewer accepts a real temporary PDF', (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: Text('Synthetic report viewer check'))));
    await tester.pumpAndSettle();
    await ReportFiles().present(syntheticPdf(),
        save: false, origin: const Rect.fromLTWH(10, 10, 100, 100));
  });
}
