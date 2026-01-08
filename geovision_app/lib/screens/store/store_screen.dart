import 'package:flutter/material.dart';

import '../../services/api_client.dart';
import 'checkout_screen.dart';

class StoreScreen extends StatefulWidget {
  const StoreScreen({super.key});

  @override
  State<StoreScreen> createState() => _StoreScreenState();
}

class _StoreScreenState extends State<StoreScreen> {
  List<StoreItem> _items = [];
  bool _loading = true;
  String? _error;

  final Map<String, int> _cart = {};

  int get _cartCount => _cart.values.fold(0, (sum, v) => sum + v);

  double get _cartTotal {
    double total = 0;
    for (final entry in _cart.entries) {
      final item = _items.firstWhere((i) => i.id == entry.key);
      total += item.price * entry.value;
    }
    return total;
  }

  void _addToCart(StoreItem item) {
    setState(() {
      _cart.update(item.id, (value) => value + 1, ifAbsent: () => 1);
    });
  }

  void _removeFromCart(String id) {
    setState(() {
      final current = _cart[id];
      if (current == null) return;
      if (current <= 1) {
        _cart.remove(id);
      } else {
        _cart[id] = current - 1;
      }
    });
  }

  @override
  void initState() {
    super.initState();
    _loadProducts();
  }

  Future<void> _loadProducts() async {
    try {
      final list = await ApiClient.instance.getJsonList('/products');
      final items = list
          .whereType<Map<String, dynamic>>()
          .map(
            (p) => StoreItem(
              id: p['id'] as String,
              category: (p['category'] as String?) ?? 'Produto',
              name: (p['name'] as String?) ?? 'Produto',
              description: (p['description'] as String?) ?? '',
              price: (p['price'] as num).toDouble(),
              unit: (p['unit'] as String?) ?? 'un',
            ),
          )
          .toList();

      if (!mounted) return;
      setState(() {
        _items = items;
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
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Loja GeoVision',
                        style: textTheme.titleLarge
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Serviços de drone, KPIs e hardware para as suas operações.',
                        style: textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                _CartSummary(
                  itemCount: _cartCount,
                  total: _cartTotal,
                  onCheckout: _cart.isEmpty
                      ? null
                      : () async {
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => CheckoutScreen(
                                items: _items,
                                quantities: Map<String, int>.from(_cart),
                              ),
                            ),
                          );
                        },
                  onClear: _cart.isEmpty
                      ? null
                      : () {
                          setState(() {
                            _cart.clear();
                          });
                        },
                ),
              ],
            ),
            const SizedBox(height: 16),
            Expanded(
              child: Builder(
                builder: (context) {
                  if (_loading) {
                    return const Center(
                      child: CircularProgressIndicator(),
                    );
                  }
                  if (_error != null) {
                    return Center(
                      child: Text(
                        'Erro ao carregar produtos:\n$_error',
                        textAlign: TextAlign.center,
                      ),
                    );
                  }
                  if (_items.isEmpty) {
                    return const Center(
                      child: Text(
                        'Nenhum produto disponível na loja.',
                      ),
                    );
                  }
                  return ListView.separated(
                    itemCount: _items.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 10),
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      final qty = _cart[item.id] ?? 0;
                      return _StoreCard(
                        item: item,
                        quantity: qty,
                        onAdd: () => _addToCart(item),
                        onRemove:
                            qty > 0 ? () => _removeFromCart(item.id) : null,
                      );
                    },
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class StoreItem {
  const StoreItem({
    required this.id,
    required this.category,
    required this.name,
    required this.description,
    required this.price,
    required this.unit,
  });

  final String id;
  final String category;
  final String name;
  final String description;
  final double price;
  final String unit;
}

class _StoreCard extends StatelessWidget {
  const _StoreCard({
    required this.item,
    required this.quantity,
    required this.onAdd,
    this.onRemove,
  });

  final StoreItem item;
  final int quantity;
  final VoidCallback onAdd;
  final VoidCallback? onRemove;

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
            item.category.toUpperCase(),
            style: textTheme.labelSmall
                ?.copyWith(color: Colors.white70, letterSpacing: 0.16),
          ),
          const SizedBox(height: 4),
          Text(
            item.name,
            style: textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            item.description,
            style: textTheme.bodySmall?.copyWith(color: Colors.white70),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'USD ${item.price.toStringAsFixed(0)}',
                    style: textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  Text(
                    item.unit,
                    style: textTheme.bodySmall?.copyWith(color: Colors.white70),
                  ),
                ],
              ),
              Row(
                children: [
                  if (onRemove != null)
                    IconButton(
                      onPressed: onRemove,
                      icon: const Icon(Icons.remove_circle_outline),
                    ),
                  Text('x$quantity'),
                  IconButton(
                    onPressed: onAdd,
                    icon: const Icon(Icons.add_circle_outline),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _CartSummary extends StatelessWidget {
  const _CartSummary({
    required this.itemCount,
    required this.total,
    this.onCheckout,
    this.onClear,
  });

  final int itemCount;
  final double total;
  final VoidCallback? onCheckout;
  final VoidCallback? onClear;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return Container(
      width: 220,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white24),
        color: Colors.white.withOpacity(0.04),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Carrinho',
                style: textTheme.labelLarge,
              ),
              Text(
                '$itemCount itens',
                style: textTheme.bodySmall?.copyWith(color: Colors.white70),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Total estimado',
                style: textTheme.bodySmall?.copyWith(color: Colors.white70),
              ),
              Text(
                'USD ${total.toStringAsFixed(0)}',
                style:
                    textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: onClear,
                  child: const Text('Limpar'),
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: ElevatedButton(
                  onPressed: onCheckout,
                  child: const Text('Checkout'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Pedido final será revisto com a equipa GeoVision.',
            style: textTheme.bodySmall
                ?.copyWith(fontSize: 10, color: Colors.white70),
          ),
        ],
      ),
    );
  }
}
