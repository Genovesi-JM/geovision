import 'package:flutter/material.dart';

import 'app.dart';
import 'services/api_client.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final hasToken = await ApiClient.instance.hasToken();
  runApp(GeoVisionApp(initialSignedIn: hasToken));
}
