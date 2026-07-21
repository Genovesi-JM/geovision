import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';

/// Exposes a simple online/offline stream for the offline-first layer.
class ConnectivityService {
  ConnectivityService([Connectivity? connectivity])
      : _connectivity = connectivity ?? Connectivity();
  final Connectivity _connectivity;

  Stream<bool> get onStatusChange => _connectivity.onConnectivityChanged
      .map((results) => !results.contains(ConnectivityResult.none));

  Future<bool> get isOnline async {
    final r = await _connectivity.checkConnectivity();
    return !r.contains(ConnectivityResult.none);
  }
}
