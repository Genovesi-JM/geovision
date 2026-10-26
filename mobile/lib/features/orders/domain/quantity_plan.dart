/// Quantities entered in the same unit; not an engineering prescription.
class QuantityPlan {
  QuantityPlan(
      {required this.need, required this.usableStock, required this.packSize}) {
    if (![need, usableStock, packSize]
            .every((v) => v.isFinite && v >= 0 && v <= 1000000) ||
        packSize == 0) {
      throw ArgumentError('Invalid quantity or pack size.');
    }
  }
  final double need;
  final double usableStock;
  final double packSize;
  double get shortfall => need > usableStock ? need - usableStock : 0;
  int get packs {
    final ratio = shortfall / packSize;
    final whole = ratio.roundToDouble();
    // Avoid an extra pack from floating-point noise, e.g. 0.14 / 0.01.
    return (ratio - whole).abs() < 1e-9 ? whole.toInt() : ratio.ceil();
  }
  double get delivered => packs * packSize;
  double get surplus => delivered > shortfall ? delivered - shortfall : 0;
}
