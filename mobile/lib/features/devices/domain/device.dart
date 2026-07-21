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
  });

  final String id;
  final String name;
  final String type; // soil_sensor|weather_station|gps_collar|thermal
  final String siteName;
  final String status; // online|offline|maintenance
  final int batteryPercent;
  final int signalPercent;
  final DateTime? lastReadingAt;
  final String? lastReadingLabel;
  final DateTime? lastMaintenanceAt;

  factory GvDevice.fromJson(Map<String, dynamic> j) => GvDevice(
        id: j['id'].toString(),
        name: (j['name'] ?? '').toString(),
        type: (j['type'] ?? 'soil_sensor').toString(),
        siteName: (j['site_name'] ?? '').toString(),
        status: (j['status'] ?? 'offline').toString(),
        batteryPercent: (j['battery_percent'] as num?)?.toInt() ?? 0,
        signalPercent: (j['signal_percent'] as num?)?.toInt() ?? 0,
        lastReadingAt: DateTime.tryParse('${j['last_reading_at'] ?? ''}'),
        lastReadingLabel: j['last_reading_label'] as String?,
        lastMaintenanceAt:
            DateTime.tryParse('${j['last_maintenance_at'] ?? ''}'),
      );
}
