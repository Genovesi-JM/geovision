import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/product.dart';

class CartController extends StateNotifier<List<CartLine>> {
  CartController() : super(const []);

  void add(GvProduct product) {
    final index = state.indexWhere((line) => line.product.id == product.id);
    if (index < 0) {
      state = [...state, CartLine(product: product, quantity: 1)];
      return;
    }
    final current = state[index];
    state = [
      for (var i = 0; i < state.length; i++)
        if (i == index)
          CartLine(product: current.product, quantity: current.quantity + 1)
        else
          state[i],
    ];
  }

  void changeQuantity(String productId, int quantity) {
    if (quantity <= 0) {
      state = state.where((line) => line.product.id != productId).toList();
      return;
    }
    state = [
      for (final line in state)
        if (line.product.id == productId)
          CartLine(product: line.product, quantity: quantity)
        else
          line,
    ];
  }

  void clear() => state = const [];
}

final cartProvider = StateNotifierProvider<CartController, List<CartLine>>(
  (ref) => CartController(),
);

final cartTotalProvider = Provider<int>(
  (ref) =>
      ref.watch(cartProvider).fold(0, (sum, line) => sum + line.totalCents),
);
