import '../../account/domain/user_profile.dart';

enum AuthMode { unknown, authenticated, demo, unauthenticated }

class AuthSession {
  const AuthSession({required this.mode, this.profile});
  final AuthMode mode;
  final UserProfile? profile;

  static const unknown = AuthSession(mode: AuthMode.unknown);
  static const unauthenticated = AuthSession(mode: AuthMode.unauthenticated);

  bool get isSignedIn =>
      mode == AuthMode.authenticated || mode == AuthMode.demo;
  bool get isDemo => mode == AuthMode.demo;
}
