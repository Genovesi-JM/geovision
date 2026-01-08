import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import 'store_screen.dart';

class CheckoutScreen extends StatefulWidget {
  const CheckoutScreen(
      {super.key, required this.items, required this.quantities});

  final List<StoreItem> items;
  final Map<String, int> quantities;

  @override
  State<CheckoutScreen> createState() => _CheckoutScreenState();
}

class _CheckoutScreenState extends State<CheckoutScreen> {
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _notesController = TextEditingController();

  bool _submitting = false;
  String? _error;

  double get _total {
    double total = 0;
    for (final entry in widget.quantities.entries) {
      final item = widget.items.firstWhere((i) => i.id == entry.key);
      total += item.price * entry.value;
    }
    return total;
  }

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });

    try {
      final itemsPayload = widget.quantities.entries.map((entry) {
        final item =
            widget.items.firstWhere((i) => i.id == entry.key, orElse: () {
          throw Exception('Produto não encontrado para o checkout.');
        });
        return {
          'product_id': item.id,
          'qty': entry.value,
        };
      }).toList();

      final payload = {
        'items': itemsPayload,
        'shipping_address': {
          'name': _nameController.text,
          'email': _emailController.text,
          'phone': _phoneController.text,
        },
        'notes': _notesController.text,
      };

      final res = await ApiClient.instance.postJson('/orders', payload);

      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Pedido enviado'),
          content: Text(
            'Pedido ${res['order_id']} criado com sucesso.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('OK'),
            ),
          ],
        ),
      );

      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
      });
    } finally {
      if (mounted) {
        setState(() {
          _submitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final cartItems = widget.items
        .where((i) => widget.quantities.containsKey(i.id))
        .map((i) => _CheckoutLine(item: i, qty: widget.quantities[i.id] ?? 0))
        .toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Checkout'),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Resumo do pedido',
                style:
                    textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              if (_error != null) ...[
                Text(
                  'Erro ao finalizar pedido: $_error',
                  style: textTheme.bodySmall?.copyWith(color: Colors.redAccent),
                ),
                const SizedBox(height: 8),
              ],
              Expanded(
                child: ListView(
                  children: [
                    for (final line in cartItems) line,
                    const SizedBox(height: 16),
                    Text(
                      'Dados de contacto',
                      style: textTheme.titleMedium
                          ?.copyWith(fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    _CheckoutForm(
                      nameController: _nameController,
                      emailController: _emailController,
                      phoneController: _phoneController,
                      notesController: _notesController,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Total estimado',
                    style: textTheme.bodyMedium,
                  ),
                  Text(
                    'USD ${_total.toStringAsFixed(0)}',
                    style: textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _submitting ? null : _submit,
                  child: _submitting
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Finalizar pedido'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CheckoutLine extends StatelessWidget {
  const _CheckoutLine({required this.item, required this.qty});

  final StoreItem item;
  final int qty;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return ListTile(
      title: Text(item.name),
      subtitle: Text('${item.category} · ${item.unit}'),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text('x$qty', style: textTheme.bodyMedium),
          Text('USD ${(item.price * qty).toStringAsFixed(0)}'),
        ],
      ),
    );
  }
}

class _CheckoutForm extends StatelessWidget {
  const _CheckoutForm({
    required this.nameController,
    required this.emailController,
    required this.phoneController,
    required this.notesController,
  });

  final TextEditingController nameController;
  final TextEditingController emailController;
  final TextEditingController phoneController;
  final TextEditingController notesController;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _CheckoutField(
          label: 'Nome / organização',
          controller: nameController,
        ),
        const SizedBox(height: 8),
        _CheckoutField(
          label: 'Email de contacto',
          controller: emailController,
        ),
        const SizedBox(height: 8),
        _CheckoutField(
          label: 'Telefone / WhatsApp',
          controller: phoneController,
        ),
        const SizedBox(height: 8),
        _CheckoutField(
          label: 'Notas para a equipa GeoVision',
          controller: notesController,
          maxLines: 3,
        ),
      ],
    );
  }
}

class _CheckoutField extends StatelessWidget {
  const _CheckoutField({
    required this.label,
    required this.controller,
    this.maxLines = 1,
  });

  final String label;
  final int maxLines;
  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Theme.of(context)
              .textTheme
              .labelSmall
              ?.copyWith(letterSpacing: 0.12, fontWeight: FontWeight.w500),
        ),
        const SizedBox(height: 4),
        TextField(
          controller: controller,
          maxLines: maxLines,
          decoration: const InputDecoration(
            isDense: true,
            border: OutlineInputBorder(),
          ),
        ),
      ],
    );
  }
}
