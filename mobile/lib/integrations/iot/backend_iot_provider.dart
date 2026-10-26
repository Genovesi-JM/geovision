import 'dart:async';

import 'package:dio/dio.dart';

import '../../core/networking/api_client.dart';
import '../../features/devices/domain/device.dart';
import 'iot_provider.dart';

/// Backend bridge for MQTT, LoRaWAN, webhooks, Modbus gateways and vendor APIs.
/// The phone never receives vendor secrets and does not maintain permanent
/// field connections. Endpoints can be implemented incrementally per provider.
class BackendIotProvider implements IotProvider {
  BackendIotProvider(this._api);
  final ApiClient _api;

  @override
  String get id => 'geovision-backend';
  @override
  bool get requiresCredentials => true;
  @override
  Set<IotTransport> get supportedTransports => const {
        IotTransport.api,
        IotTransport.mqtt,
        IotTransport.webhook,
        IotTransport.bluetooth,
        IotTransport.lorawan,
        IotTransport.modbusGateway,
      };

  @override
  Future<List<GvDevice>> fetchDevices() async {
    final response = await _api.raw.get('/mobile/devices');
    final rows = response.data is Map
        ? (response.data['items'] as List? ?? const [])
        : (response.data as List? ?? const []);
    return rows
        .whereType<Map>()
        .map((row) => GvDevice.fromJson(Map<String, dynamic>.from(row)))
        .toList();
  }

  @override
  Stream<DeviceReading> subscribeReadings(String deviceId) async* {
    // Safe polling fallback. A WebSocket/SSE transport can replace it without
    // changing repositories or screens.
    while (true) {
      final response = await _api.raw.get('/iot/devices/$deviceId/latest');
      final data = Map<String, dynamic>.from(response.data as Map);
      yield DeviceReading(
        deviceId: deviceId,
        label: (data['label'] ?? data['value'] ?? '').toString(),
        at: DateTime.tryParse('${data['at'] ?? ''}'),
      );
      await Future<void>.delayed(const Duration(seconds: 30));
    }
  }

  @override
  Future<IotOperationResult> diagnose(String deviceId) =>
      _operation('/iot/devices/$deviceId/diagnose');

  @override
  Future<IotOperationResult> provision(DeviceProvisioningRequest request) =>
      _operation('/iot/devices/${request.deviceId}/provision', data: {
        'site_id': request.siteId,
        'transport': request.transport.name,
        'configuration': request.configuration,
      });

  @override
  Future<IotOperationResult> sendCommand(DeviceCommand command) =>
      _operation('/iot/devices/${command.deviceId}/commands', data: {
        'name': command.name,
        'arguments': Map<String, Object?>.from(command.arguments)
          ..remove('confirmed'),
        'reason': command.reason.trim(),
        'confirmed': command.arguments['confirmed'] == true,
      });

  Future<IotOperationResult> _operation(String path,
      {Map<String, Object?>? data}) async {
    try {
      final response = await _api.raw.post(path, data: data);
      final body = response.data is Map
          ? Map<String, dynamic>.from(response.data as Map)
          : <String, dynamic>{};
      return IotOperationResult(
        _outcome('${body['outcome'] ?? 'error'}'),
        message: body['message']?.toString(),
        retryable: !path.endsWith('/commands') && body['retryable'] == true,
        data: Map<String, Object?>.from(body['data'] as Map? ?? body),
      );
    } on DioException catch (error) {
      final code = error.response?.statusCode;
      if (code == 401) {
        return const IotOperationResult(IotOutcome.credentialsRequired,
            message: 'Provider authorization is required.');
      }
      if (code == 403) {
        return const IotOperationResult(IotOutcome.permissionRequired,
            message: 'Your role does not allow this operation.');
      }
      if (code == 404) {
        return const IotOperationResult(IotOutcome.notFound,
            message: 'This device or operation is unavailable.');
      }
      if (code == 422) {
        return const IotOperationResult(IotOutcome.invalidInput,
            message: 'Review the command details and reason.');
      }
      if (code == 409) {
        return const IotOperationResult(IotOutcome.rejected,
            message:
                'The device conditions do not allow this command. Refresh its status.');
      }
      if (error.type == DioExceptionType.connectionTimeout ||
          error.type == DioExceptionType.receiveTimeout ||
          error.type == DioExceptionType.sendTimeout) {
        return IotOperationResult(IotOutcome.timeout,
            message:
                'No confirmation received. Check device state before sending another command.',
            retryable: !path.endsWith('/commands'));
      }
      if (error.type == DioExceptionType.connectionError) {
        return IotOperationResult(IotOutcome.offline,
            message: 'The GeoVision IoT bridge is offline.',
            retryable: !path.endsWith('/commands'));
      }
      return IotOperationResult(IotOutcome.error,
          message: _api.mapError(error).message,
          retryable: !path.endsWith('/commands'));
    } catch (error) {
      return IotOperationResult(IotOutcome.error,
          message: '$error', retryable: !path.endsWith('/commands'));
    }
  }

  IotOutcome _outcome(String value) => switch (value) {
        'success' => IotOutcome.success,
        'pending' => IotOutcome.pending,
        'offline' => IotOutcome.offline,
        'permission_required' => IotOutcome.permissionRequired,
        'credentials_required' => IotOutcome.credentialsRequired,
        'unsupported' => IotOutcome.unsupported,
        'rejected' => IotOutcome.rejected,
        'timeout' => IotOutcome.timeout,
        _ => IotOutcome.error,
      };
}
