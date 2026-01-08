class ApiConfig {
  const ApiConfig._();

  /// Base URL for the GeoVision backend.
  ///
  /// For Android emulator use http://10.0.2.2:8010
  /// For iOS simulator use http://127.0.0.1:8010 (with port forwarded)
  /// Adjust as needed for your environment.
  static const String baseUrl = 'http://10.0.2.2:8010';
}
