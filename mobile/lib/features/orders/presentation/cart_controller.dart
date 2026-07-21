import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/orders_repository.dart';
import '../domain/currency.dart';
import '../domain/product.dart';

class CartController extends StateNotifier<List<CartLine>> {
  CartController([this._repository, this._ref]) : super(const []) {
    unawaited(_hydrate());
  }
  final OrdersRepository? _repository;
  final Ref? _ref;

  void add(GvProduct product) {
    final index = state.indexWhere((line) => line.product.id == product.id);
    if (index < 0) {
      state = [...state, CartLine(product: product, quantity: 1)];
      _syncAdd(product);
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
    _syncAdd(product);
  }

  void changeQuantity(String productId, int quantity) {
    if (quantity <= 0) {
      state = state.where((line) => line.product.id != productId).toList();
      _syncQuantity(productId, quantity);
      return;
    }
    state = [
      for (final line in state)
        if (line.product.id == productId)
          CartLine(product: line.product, quantity: quantity)
        else
          line,
    ];
    _syncQuantity(productId, quantity);
  }

  void clear() => state = const [];

  Future<void> _hydrate() async {
    final repository = _repository;
    if (repository == null || repository.isDemo) return;
    try {
      final products = await repository.catalogue();
      final cart = await repository.loadCart();
      if (cart == null || !mounted) return;
      final productsById = {
        for (final product in products) product.id: product
      };
      state = [
        for (final item in cart.items)
          if (productsById[item.productId] != null)
            CartLine(
                product: productsById[item.productId]!,
                quantity: item.quantity),
      ];
    } catch (error, stack) {
      final ref = _ref;
      if (ref != null) {
        ref.read(cartSyncProvider.notifier).state = AsyncError(error, stack);
      }
    }
  }

  Future<void> changeCurrency(StoreCurrency currency) async {
    final repository = _repository;
    if (repository == null || repository.isDemo) return;
    await _runSync(() => repository.updateCurrency(switch (currency) {
          StoreCurrency.akz => 'AOA',
          StoreCurrency.eur => 'EUR',
          StoreCurrency.usd => 'USD',
        }));
  }

  void _syncAdd(GvProduct product) {
    final repository = _repository;
    if (repository == null || repository.isDemo) return;
    unawaited(_runSync(() => repository.addToCart(
          product,
          1,
          _apiCurrency,
        )));
  }

  void _syncQuantity(String productId, int quantity) {
    final repository = _repository;
    if (repository == null || repository.isDemo) return;
    unawaited(_runSync(() => repository.updateQuantity(productId, quantity)));
  }

  String get _apiCurrency =>
      switch (_ref?.read(storeCurrencyProvider) ?? StoreCurrency.akz) {
        StoreCurrency.akz => 'AOA',
        StoreCurrency.eur => 'EUR',
        StoreCurrency.usd => 'USD',
      };

  Future<void> _runSync(Future<Object?> Function() operation) async {
    final ref = _ref;
    if (ref != null) {
      ref.read(cartSyncProvider.notifier).state = const AsyncLoading();
    }
    try {
      await operation();
      if (ref != null) {
        ref.read(cartSyncProvider.notifier).state = const AsyncData(null);
      }
    } catch (error, stack) {
      if (ref != null) {
        ref.read(cartSyncProvider.notifier).state = AsyncError(error, stack);
      }
    }
  }
}

final cartProvider = StateNotifierProvider<CartController, List<CartLine>>(
  (ref) => CartController(ref.watch(ordersRepositoryProvider), ref),
);

final cartSyncProvider = StateProvider<AsyncValue<void>>(
  (ref) => const AsyncData(null),
);

final cartTotalProvider = Provider<int>(
  (ref) =>
      ref.watch(cartProvider).fold(0, (sum, line) => sum + line.totalCents),
);
