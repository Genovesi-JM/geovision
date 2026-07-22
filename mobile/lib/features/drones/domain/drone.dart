class GvDrone {
  const GvDrone({
    required this.id,
    required this.name,
    required this.model,
    required this.provider,
    required this.connectionMode,
    required this.sdkSupported,
    required this.status,
    this.serialNumber,
    this.siteId,
    this.capabilities = const [],
  });

  final String id;
  final String name;
  final String model;
  final String provider;
  final String connectionMode;
  final bool sdkSupported;
  final String status;
  final String? serialNumber;
  final String? siteId;
  final List<String> capabilities;

  factory GvDrone.fromJson(Map<String, dynamic> json) => GvDrone(
        id: '${json['id']}',
        name: '${json['name']}',
        model: '${json['model']}',
        provider: '${json['provider'] ?? 'manual_import'}',
        connectionMode: '${json['connection_mode'] ?? 'media_import'}',
        sdkSupported: json['sdk_supported'] == true,
        status: '${json['status'] ?? 'registered'}',
        serialNumber: json['serial_number']?.toString(),
        siteId: json['site_id']?.toString(),
        capabilities: (json['capabilities'] as List? ?? const [])
            .map((value) => '$value')
            .toList(),
      );
}

class DroneMission {
  const DroneMission({
    required this.id,
    required this.siteId,
    required this.aircraftId,
    required this.name,
    required this.type,
    required this.status,
    required this.altitudeM,
    required this.frontOverlap,
    required this.sideOverlap,
  });

  final String id;
  final String siteId;
  final String aircraftId;
  final String name;
  final String type;
  final String status;
  final int altitudeM;
  final int frontOverlap;
  final int sideOverlap;

  factory DroneMission.fromJson(Map<String, dynamic> json) => DroneMission(
        id: '${json['id']}',
        siteId: '${json['site_id']}',
        aircraftId: '${json['aircraft_id']}',
        name: '${json['name']}',
        type: '${json['mission_type']}',
        status: '${json['status']}',
        altitudeM: (json['altitude_m'] as num?)?.toInt() ?? 80,
        frontOverlap: (json['front_overlap_percent'] as num?)?.toInt() ?? 80,
        sideOverlap: (json['side_overlap_percent'] as num?)?.toInt() ?? 70,
      );
}

enum DroneOutcome {
  ready,
  mediaImportOnly,
  credentialsRequired,
  permissionRequired,
  providerUnavailable,
  unsupported,
  safetyCheckRequired,
  pilotHandoffRequired,
  offline,
  error,
}

class DroneOperationResult {
  const DroneOperationResult(this.outcome, this.message,
      {this.retryable = false});
  final DroneOutcome outcome;
  final String message;
  final bool retryable;
}
