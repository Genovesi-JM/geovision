class GvDevice {
  const GvDevice({
    required this.id,
    required this.name,
    required this.type,
    required this.siteName,
    required this.status,
    required this.batteryPercent,
    required this.signalPercent,
    this.lastReadingAt,
    this.lastReadingLabel,
    this.lastMaintenanceAt,
    this.providerId = 'unknown',
    this.assetId,
    this.transport = 'api',
    this.capabilities = const [],
    this.integrationMessage,
  });

  final String? assetId;
  final String id;
  final String name;
  final String type; // soil_sensor|weather_station|gps_collar|thermal
  final String siteName;
  final String status; // online|offline|maintenance
  final int? batteryPercent;
  final int? signalPercent;
  final DateTime? lastReadingAt;
  final String? lastReadingLabel;
  final DateTime? lastMaintenanceAt;
  final String providerId;
  final String transport; // api|mqtt|webhook|ble|lorawan|modbus_gateway
  final List<String> capabilities;
  final String? integrationMessage;

  static int? _percent(Object? value) =>
      value is num && value.isFinite && value >= 0 && value <= 100
          ? value.toInt()
          : null;

  factory GvDevice.fromJson(Map<String, dynamic> j) => GvDevice(
        id: j['id'].toString(),
        name: (j['name'] ?? '').toString(),
        type: (j['type'] ?? 'soil_sensor').toString(),
        siteName: (j['site_name'] ?? '').toString(),
        assetId: j['core_asset_id']?.toString(),
        status: (j['status'] ?? 'unknown').toString(),
        batteryPercent: _percent(j['battery_percent']),
        signalPercent: _percent(j['signal_percent']),
        lastReadingAt: DateTime.tryParse('${j['last_reading_at'] ?? ''}'),
        lastReadingLabel: j['last_reading_label'] as String?,
        lastMaintenanceAt:
            DateTime.tryParse('${j['last_maintenance_at'] ?? ''}'),
        providerId: (j['provider_id'] ?? 'unknown').toString(),
        transport: (j['transport'] ?? 'api').toString(),
        capabilities: (j['capabilities'] as List?)
                ?.map((value) => value.toString())
                .toList() ??
            const [],
        integrationMessage: j['integration_message'] as String?,
      );
}
