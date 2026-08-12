import '../../../core/config/app_config.dart';
import '../../../core/errors/failures.dart';
import '../../../core/errors/result.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/storage/secure_token_store.dart';
import '../../../core/utils/app_logger.dart';
import '../../account/domain/user_profile.dart';
import '../domain/auth_session.dart';
import '../domain/registration_request.dart';

/// Talks to the existing GeoVision FastAPI auth endpoints
/// (/auth/login, /auth/refresh, /auth/logout, /auth/me). Tokens are stored in
/// the platform secure enclave; passwords are never persisted or logged.
class AuthRepository {
  AuthRepository({
    required ApiClient api,
    required SecureTokenStore tokenStore,
    required AppConfig config,
  })  : _api = api,
        _tokens = tokenStore,
        _config = config;

  final ApiClient _api;
  final SecureTokenStore _tokens;
  final AppConfig _config;
  final _log = const AppLogger('AuthRepo');

  Future<AuthSession> restoreSession() async {
    if (await _tokens.hasSession) {
      final me = await fetchProfile();
      return me.when(
        ok: (p) => AuthSession(mode: AuthMode.authenticated, profile: p),
        err: (_) => AuthSession.unauthenticated,
      );
    }
    return AuthSession.unauthenticated;
  }

  Future<Result<AuthSession>> login(String email, String password) async {
    try {
      final res = await _api.raw.post('/auth/login', data: {
        'email': email.trim().toLowerCase(),
        'password': password,
      });
      final data = res.data as Map<String, dynamic>;
      final access = data['access_token'] as String?;
      final refresh = data['refresh_token'] as String?;
      if (access == null || refresh == null) {
        return const Err(ServerFailure('Malformed login response.'));
      }
      await _tokens.saveTokens(access: access, refresh: refresh);
      final profile = UserProfile.fromJson(data);
      _log.info('Login successful.');
      return Ok(AuthSession(mode: AuthMode.authenticated, profile: profile));
    } catch (e) {
      return Err(_api.mapError(e));
    }
  }

  Future<Result<AuthSession>> register(RegistrationRequest request) async {
    try {
      final res = await _api.raw.post('/auth/register', data: request.toJson());
      final data = Map<String, dynamic>.from(res.data as Map);
      final access = data['access_token'] as String?;
      final refresh = data['refresh_token'] as String?;
      if (access == null || refresh == null) {
        return const Err(ServerFailure('Malformed registration response.'));
      }
      await _tokens.saveTokens(access: access, refresh: refresh);
      final profile = UserProfile.fromJson(data);
      _log.info('Account created successfully.');
      return Ok(AuthSession(mode: AuthMode.authenticated, profile: profile));
    } catch (e) {
      return Err(_api.mapError(e));
    }
  }

  AuthSession enterDemo() {
    _log.info('Entering demo mode.');
    return const AuthSession(
      mode: AuthMode.demo,
      profile: UserProfile(
        id: 'demo',
        email: 'demo@geovisionops.com',
        fullName: 'Demo Operator',
        organisation: 'Fazenda Kilombo Agro',
        customerType: 'farm',
        dashboardProfile: 'farm',
        sectors: ['agro'],
        useCases: ['soil', 'water', 'weather'],
      ),
    );
  }

  Future<Result<UserProfile>> fetchProfile() async {
    try {
      final res = await _api.raw.get('/auth/me');
      return Ok(UserProfile.fromJson(res.data as Map<String, dynamic>));
    } catch (e) {
      return Err(_api.mapError(e));
    }
  }

  Future<Result<void>> forgotPassword(String email) async {
    try {
      await _api.raw.post('/auth/forgot-password',
          data: {'email': email.trim().toLowerCase()});
      return const Ok(null);
    } catch (e) {
      return Err(_api.mapError(e));
    }
  }

  Future<Result<void>> resetPassword(String token, String password) async {
    try {
      await _api.raw.post('/auth/reset-password', data: {
        'token': token,
        'new_password': password,
      });
      return const Ok(null);
    } catch (e) {
      return Err(_api.mapError(e));
    }
  }

  Future<void> logout() async {
    final refresh = await _tokens.readRefresh();
    try {
      if (!_config.demoMode && refresh != null) {
        await _api.raw.post('/auth/logout', data: {'refresh_token': refresh});
      }
    } catch (_) {
      // best-effort; always clear locally
    } finally {
      await _tokens.clear();
      _log.info('Session cleared at logout.');
    }
  }
}
