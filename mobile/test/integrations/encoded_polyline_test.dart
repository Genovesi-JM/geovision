import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/integrations/maps/encoded_polyline.dart';

void main() {
  test('decodes a valid provider route', () {
    final points = decodeEncodedPolyline('_p~iF~ps|U_ulLnnqC_mqNvxq`@');

    expect(points, hasLength(3));
    expect(points.first.latitude, closeTo(38.5, 0.00001));
    expect(points.first.longitude, closeTo(-120.2, 0.00001));
    expect(points.last.latitude, closeTo(43.252, 0.00001));
    expect(points.last.longitude, closeTo(-126.453, 0.00001));
  });

  test('rejects malformed, oversized, and out-of-range routes', () {
    expect(decodeEncodedPolyline(null), isEmpty);
    expect(decodeEncodedPolyline('abc'), isEmpty);
    expect(decodeEncodedPolyline('~' * 4097), isEmpty);
    expect(decodeEncodedPolyline('_cidP?_cidP?'), isEmpty);
  });
}
