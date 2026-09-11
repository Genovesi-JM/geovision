import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geovision/app/app.dart';
import 'package:geovision/app/providers.dart';
import 'package:geovision/core/config/app_config.dart';
import 'package:geovision/core/config/app_flavor.dart';
import 'package:geovision/core/storage/secure_token_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _config = AppConfig(
  flavor: AppFlavor.dev,
  apiBaseUrl: 'http://127.0.0.1:8010',
  demoMode: true,
  connectTimeout: Duration(seconds: 5),
  receiveTimeout: Duration(seconds: 5),
  mapProvider: 'demo',
  paymentProvider: 'mock',
  pushProvider: 'mock',
  enableBiometricUnlock: false,
);

void main() {
  final captureDirectory = Platform.environment['GV_SCREENSHOT_DIR'];
  final profiles = <String, Size>{
    'ios-compact': const Size(320, 568),
    'android-standard': const Size(412, 915),
  };

  for (final profile in profiles.entries) {
    testWidgets('capture ${profile.key} visual audit', (tester) async {
      final boundaryKey = GlobalKey();
      tester.view
        ..physicalSize = profile.value
        ..devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      SharedPreferences.setMockInitialValues({'gv_preferred_language': 'es'});
      final prefs = await SharedPreferences.getInstance();
      await tester.pumpWidget(
        RepaintBoundary(
          key: boundaryKey,
          child: ProviderScope(
            overrides: [
              appConfigProvider.overrideWithValue(_config),
              sharedPrefsProvider.overrideWithValue(prefs),
              secureTokenStoreProvider.overrideWithValue(_EmptyTokenStore()),
              connectivityStatusProvider
                  .overrideWith((ref) => Stream.value(true)),
            ],
            child: const GeoVisionApp(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.runAsync(
        () => _capture(
          boundaryKey,
          '$captureDirectory/${profile.key}-home.png',
        ),
      );
      for (final destination in {
        'assets': 'Activos',
        'actions': 'Acciones',
        'services': 'Servicios',
        'more': 'Más',
      }.entries) {
        await tester.tap(find.text(destination.value).last);
        await tester.pumpAndSettle();
        await tester.runAsync(
          () => _capture(
            boundaryKey,
            '$captureDirectory/${profile.key}-${destination.key}.png',
          ),
        );
      }
    }, skip: captureDirectory == null);
  }
}

class _EmptyTokenStore extends SecureTokenStore {
  @override
  Future<bool> get hasSession async => false;
}

Future<void> _capture(GlobalKey key, String path) async {
  final boundary =
      key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
  final image = await boundary.toImage(pixelRatio: 2);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  final file = File(path);
  await file.parent.create(recursive: true);
  await file.writeAsBytes(data!.buffer.asUint8List(), flush: true);
}
