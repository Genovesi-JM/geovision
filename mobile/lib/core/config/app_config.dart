import 'app_flavor.dart';

/// Centralised, immutable runtime configuration.
///
/// All values are provided via `--dart-define` so no secrets are ever
/// committed to source. Sensible non-secret defaults keep the app runnable
/// in demo mode with zero configuration.
class AppConfig {
  const AppConfig({
    required this.flavor,
    required this.apiBaseUrl,
    required this.demoMode,
    required this.connectTimeout,
    required this.receiveTimeout,
    required this.mapProvider,
    required this.paymentProvider,
    required this.pushProvider,
    required this.enableBiometricUnlock,
  });

  final AppFlavor flavor;
  final String apiBaseUrl;

  /// When true the app is fully usable without any backend or provider
  /// credentials. Repositories resolve to in-memory demo data sources.
  final bool demoMode;

  final Duration connectTimeout;
  final Duration receiveTimeout;

  /// Feature-flag style selectors for pluggable provider adapters.
  final String mapProvider; // demo | mapbox | arcgis
  final String paymentProvider; // mock | stripe | multicaixa | bank_transfer
  final String pushProvider; // mock | apns | fcm

  final bool enableBiometricUnlock;

  static const _localApi = 'http://127.0.0.1:8010';
  static const _prodApi = 'https://api.geovisionops.com';

  /// Build the configuration from compile-time environment values.
  factory AppConfig.fromEnvironment() {
    const flavorStr = String.fromEnvironment('GV_FLAVOR', defaultValue: 'dev');
    final flavor = appFlavorFromString(flavorStr);

    final defaultApi = flavor.isProduction ? _prodApi : _localApi;
    const apiOverride = String.fromEnvironment('GV_API_BASE_URL');

    // Demo mode defaults ON for dev/staging so the app always runs; can be
    // forced off with --dart-define=GV_DEMO_MODE=false.
    const demoOverride = String.fromEnvironment('GV_DEMO_MODE');
    final demo = demoOverride.isEmpty
        ? !flavor.isProduction
        : demoOverride.toLowerCase() == 'true';

    return AppConfig(
      flavor: flavor,
      apiBaseUrl: apiOverride.isEmpty ? defaultApi : apiOverride,
      demoMode: demo,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 20),
      mapProvider:
          const String.fromEnvironment('GV_MAP_PROVIDER', defaultValue: 'demo'),
      paymentProvider: const String.fromEnvironment('GV_PAYMENT_PROVIDER',
          defaultValue: 'mock'),
      pushProvider: const String.fromEnvironment('GV_PUSH_PROVIDER',
          defaultValue: 'mock'),
      enableBiometricUnlock:
          const bool.fromEnvironment('GV_BIOMETRIC', defaultValue: false),
    );
  }
}
