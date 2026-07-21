import 'package:dio/dio.dart';

import '../config/app_config.dart';
import '../errors/failures.dart';
import '../storage/secure_token_store.dart';
import '../utils/app_logger.dart';

/// Thin wrapper over Dio that centralises base URL, timeouts, bearer-token
/// injection, and transparent access-token refresh. Never logs token values.
class ApiClient {
  ApiClient({
    required AppConfig config,
    required SecureTokenStore tokenStore,
    Dio? dio,
  })  : _config = config,
        _tokenStore = tokenStore,
        _dio = dio ?? Dio() {
    _dio.options
      ..baseUrl = config.apiBaseUrl
      ..connectTimeout = config.connectTimeout
      ..receiveTimeout = config.receiveTimeout
      ..headers['Content-Type'] = 'application/json';
    _dio.interceptors.add(_authInterceptor());
  }

  final AppConfig _config;
  final SecureTokenStore _tokenStore;
  final Dio _dio;
  final _log = const AppLogger('ApiClient');

  Dio get raw => _dio;

  InterceptorsWrapper _authInterceptor() => InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await _tokenStore.readAccess();
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (err, handler) async {
          // Attempt one transparent refresh on 401, then replay the request.
          if (err.response?.statusCode == 401) {
            final refreshed = await _tryRefresh();
            if (refreshed) {
              try {
                final clone = await _replay(err.requestOptions);
                return handler.resolve(clone);
              } catch (_) {/* fall through */}
            }
          }
          handler.next(err);
        },
      );

  Future<bool> _tryRefresh() async {
    final refresh = await _tokenStore.readRefresh();
    if (refresh == null) return false;
    try {
      final res = await Dio(BaseOptions(baseUrl: _config.apiBaseUrl))
          .post('/auth/refresh', data: {'refresh_token': refresh});
      final access = res.data['access_token'] as String?;
      final newRefresh = res.data['refresh_token'] as String?;
      if (access == null) return false;
      await _tokenStore.saveTokens(
          access: access, refresh: newRefresh ?? refresh);
      _log.info('Access token refreshed.');
      return true;
    } catch (e) {
      _log.warn('Token refresh failed; session will be cleared.');
      await _tokenStore.clear();
      return false;
    }
  }

  Future<Response<dynamic>> _replay(RequestOptions ro) {
    return _dio.fetch(ro);
  }

  /// Maps DioException into a typed [Failure].
  Failure mapError(Object error) {
    if (error is DioException) {
      switch (error.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.receiveTimeout:
        case DioExceptionType.sendTimeout:
          return const TimeoutFailure();
        case DioExceptionType.connectionError:
          return const NetworkFailure();
        case DioExceptionType.badResponse:
          final code = error.response?.statusCode;
          if (code == 401) return const UnauthorizedFailure();
          final detail = error.response?.data is Map
              ? (error.response?.data['detail']?.toString())
              : null;
          return ServerFailure(detail ?? 'Server error ($code).',
              statusCode: code);
        default:
          return UnknownFailure(
            message: error.message ?? 'Network error.',
            cause: error,
          );
      }
    }
    return UnknownFailure(message: '$error', cause: error);
  }
}
