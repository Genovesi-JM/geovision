import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Stores auth tokens in the platform secure enclave (Keychain / Keystore).
/// Passwords are NEVER stored. Tokens are never logged.
class SecureTokenStore {
  SecureTokenStore([FlutterSecureStorage? storage])
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
              iOptions:
                  IOSOptions(accessibility: KeychainAccessibility.first_unlock),
            );

  final FlutterSecureStorage _storage;

  static const _kAccess = 'gv_access_token';
  static const _kRefresh = 'gv_refresh_token';

  Future<void> saveTokens(
      {required String access, required String refresh}) async {
    await _storage.write(key: _kAccess, value: access);
    await _storage.write(key: _kRefresh, value: refresh);
  }

  Future<String?> readAccess() => _storage.read(key: _kAccess);
  Future<String?> readRefresh() => _storage.read(key: _kRefresh);

  Future<void> updateAccess(String access) =>
      _storage.write(key: _kAccess, value: access);

  Future<bool> get hasSession async => (await readAccess()) != null;

  /// Securely clears all session material at logout.
  Future<void> clear() async {
    await _storage.delete(key: _kAccess);
    await _storage.delete(key: _kRefresh);
  }
}
