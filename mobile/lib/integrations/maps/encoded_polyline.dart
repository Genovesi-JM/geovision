import 'package:latlong2/latlong.dart';

/// Decodes Google's encoded polyline format without accepting unbounded or
/// out-of-range provider data.
List<LatLng> decodeEncodedPolyline(String? value) {
  if (value == null || value.length < 2 || value.length > 4096) return const [];
  final points = <LatLng>[];
  var index = 0;
  var latitude = 0;
  var longitude = 0;

  int? readDelta() {
    var result = 0;
    var shift = 0;
    while (index < value.length && shift <= 30) {
      final chunk = value.codeUnitAt(index++) - 63;
      if (chunk < 0 || chunk > 63) return null;
      result |= (chunk & 0x1f) << shift;
      if (chunk < 0x20) return result.isOdd ? ~(result >> 1) : result >> 1;
      shift += 5;
    }
    return null;
  }

  while (index < value.length && points.length < 2048) {
    final latitudeDelta = readDelta();
    final longitudeDelta = readDelta();
    if (latitudeDelta == null || longitudeDelta == null) return const [];
    latitude += latitudeDelta;
    longitude += longitudeDelta;
    final point = LatLng(latitude / 1e5, longitude / 1e5);
    if (point.latitude.abs() > 90 || point.longitude.abs() > 180) {
      return const [];
    }
    points.add(point);
  }
  return index == value.length && points.length >= 2 ? points : const [];
}
