import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/localization/journey_copy.dart';
import '../domain/quantity_plan.dart';

class QuantityScreen extends StatefulWidget {
  const QuantityScreen({super.key});
  @override
  State<QuantityScreen> createState() => _QuantityScreenState();
}

class _QuantityScreenState extends State<QuantityScreen> {
  final need = TextEditingController(),
      stock = TextEditingController(),
      pack = TextEditingController();
  bool compatible = false;
  String unit = 'm';
  @override
  void dispose() {
    need.dispose();
    stock.dispose();
    pack.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    String t(String pt, String es, String en) =>
        journeyText(context, es, en, pt: pt);
    double? number(TextEditingController c) =>
        double.tryParse(c.text.replaceAll(',', '.'));
    QuantityPlan? plan;
    if (compatible && [need, stock, pack].every((c) => number(c) != null)) {
      try {
        plan = QuantityPlan(
            need: number(need)!,
            usableStock: number(stock)!,
            packSize: number(pack)!);
      } on ArgumentError {/* Validation is shown below. */}
    }
    final result = plan;
    String amount(double value) => value.toStringAsFixed(2);
    Widget field(TextEditingController c, String label) => Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: TextField(
            controller: c,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(labelText: label, suffixText: unit)));
    return Scaffold(
        appBar: AppBar(
            title: Text(t(
                'Só o necessário', 'Solo lo necesario', 'Only what you need'))),
        body: ListView(padding: const EdgeInsets.all(24), children: [
          Text(
              t('Comece pelo que já tem.', 'Empieza por lo que ya tienes.',
                  'Start with what you already have.'),
              style: Theme.of(context).textTheme.headlineSmall),
          const SizedBox(height: 12),
          Text(t(
              'Use uma necessidade medida e stock compatível em boas condições. Não acrescentamos uma margem automática. Confirme a embalagem com o fornecedor.',
              'Usa una necesidad medida y existencias compatibles en buen estado. Sin margen automático. Confirma el envase con el proveedor.',
              'Use a measured need and compatible stock in good condition. No automatic reserve. Confirm pack size with the supplier.')),
          DropdownButton<String>(
              value: unit,
              items: ['m', 'un.', 'kg', 'L']
                  .map((u) => DropdownMenuItem(value: u, child: Text(u)))
                  .toList(),
              onChanged: (v) => setState(() {
                    unit = v!;
                    need.clear();
                    stock.clear();
                    pack.clear();
                    compatible = false;
                  })),
          field(need, t('Necessidade total', 'Necesidad total', 'Total need')),
          field(stock,
              t('Stock utilizável', 'Existencias utilizables', 'Usable stock')),
          field(
              pack,
              t('Quantidade por embalagem', 'Cantidad por envase',
                  'Quantity per pack')),
          CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: compatible,
              onChanged: (v) => setState(() => compatible = v ?? false),
              title: Text(t(
                  'Confirmei a compatibilidade e a unidade.',
                  'He confirmado la compatibilidad y la unidad.',
                  'I confirmed compatibility and units.'))),
          if (result == null)
            Text(t(
                'Preencha os valores e confirme a compatibilidade. Embalagem superior a zero; máximo 1 000 000 por campo.',
                'Completa los valores y confirma compatibilidad. Envase superior a cero; máximo 1 000 000 por campo.',
                'Enter values and confirm compatibility. Pack size above zero; maximum 1,000,000 per field.')),
          if (result != null) ...[
            const Divider(),
            Text(
                result.packs == 0
                    ? t('Não precisa de comprar.', 'No necesitas comprar.',
                        'No purchase needed.')
                    : '${result.packs} ${t('embalagens', 'envases', 'packs')}',
                style: Theme.of(context).textTheme.headlineSmall),
            ListTile(
                title: Text(t('Em falta', 'Falta', 'Shortfall')),
                trailing: Text('${amount(result.shortfall)} $unit')),
            ListTile(
                title: Text(t('A receber', 'A recibir', 'To receive')),
                trailing: Text('${amount(result.delivered)} $unit')),
            ListTile(
                title: Text(t('Excedente', 'Excedente', 'Surplus')),
                trailing: Text('${amount(result.surplus)} $unit')),
            Text(t(
                'Estimativa de quantidade. Preço, entrega e adequação técnica por confirmar. Compare outros formatos.',
                'Estimación de cantidad. Precio, entrega e idoneidad técnica por confirmar. Compara otros formatos.',
                'Quantity estimate. Price, delivery and technical suitability remain to be confirmed. Compare other pack sizes.')),
            if (result.packs > 0)
              FilledButton(
                  onPressed: () =>
                      context.push(Uri(path: '/work/new', queryParameters: {
                        'description':
                            '${t('Verificar quantidade', 'Verificar cantidad', 'Verify quantity')}: ${result.packs} × ${amount(result.packSize)} $unit; ${t('necessidade', 'necesidad', 'need')} ${amount(result.need)} $unit; stock ${amount(result.usableStock)} $unit.'
                      }).toString()),
                  child: Text(t('Pedir avaliação', 'Solicitar evaluación',
                      'Request assessment'))),
          ],
        ]));
  }
}
