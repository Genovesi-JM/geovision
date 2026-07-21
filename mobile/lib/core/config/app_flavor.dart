/// Build flavors / environments for GeoVision.
///
/// Select at build time with:
///   flutter run --dart-define=GV_FLAVOR=dev
///   flutter run --dart-define=GV_FLAVOR=staging
///   flutter run --dart-define=GV_FLAVOR=prod
enum AppFlavor { dev, staging, prod }

AppFlavor appFlavorFromString(String value) {
  switch (value.toLowerCase()) {
    case 'prod':
    case 'production':
      return AppFlavor.prod;
    case 'staging':
    case 'stg':
      return AppFlavor.staging;
    case 'dev':
    case 'development':
    default:
      return AppFlavor.dev;
  }
}

extension AppFlavorX on AppFlavor {
  bool get isProduction => this == AppFlavor.prod;
  bool get showEnvironmentBanner => this != AppFlavor.prod;

  String get label {
    switch (this) {
      case AppFlavor.dev:
        return 'DEV';
      case AppFlavor.staging:
        return 'STAGING';
      case AppFlavor.prod:
        return 'PROD';
    }
  }
}
