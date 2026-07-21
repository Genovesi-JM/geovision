import '../../features/orders/domain/product.dart';

/// Provider boundary for delivery tracking. The demo implementation keeps the
/// app credential-free; Google Maps or a logistics API can implement this same
/// contract later without changing the customer screens.
abstract interface class DeliveryTrackingProvider {
  String get id;
  Future<GvDelivery?> track(String trackingCode);
}

class DemoDeliveryTrackingProvider implements DeliveryTrackingProvider {
  const DemoDeliveryTrackingProvider(this.deliveries);
  final List<GvDelivery> deliveries;
  @override
  String get id => 'demo-route-map';
  @override
  Future<GvDelivery?> track(String trackingCode) async {
    for (final delivery in deliveries) {
      if (delivery.trackingCode == trackingCode) return delivery;
    }
    return null;
  }
}

/// Production integration seam. Requires Google Maps keys and logistics data.
class GoogleMapsDeliveryTrackingProvider implements DeliveryTrackingProvider {
  const GoogleMapsDeliveryTrackingProvider();
  @override
  String get id => 'google-maps-not-configured';
  @override
  Future<GvDelivery?> track(String trackingCode) =>
      throw StateError('Google Maps delivery tracking is not configured.');
}
