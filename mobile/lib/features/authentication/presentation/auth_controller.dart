import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/errors/result.dart';
import '../data/auth_repository.dart';
import '../domain/auth_session.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) => AuthRepository(
      api: ref.watch(apiClientProvider),
      tokenStore: ref.watch(secureTokenStoreProvider),
      config: ref.watch(appConfigProvider),
    ));

class AuthController extends StateNotifier<AuthSession> {
  AuthController(this._repo, {required bool demoMode})
      : super(AuthSession.unknown) {
    _init(demoMode);
  }
  final AuthRepository _repo;

  Future<void> _init(bool demoMode) async {
    // In demo builds we auto-enter demo so the whole app is explorable, but
    // the login screen is still reachable from Account.
    final restored = await _repo.restoreSession();
    if (restored.isSignedIn) {
      state = restored;
    } else if (demoMode) {
      state = _repo.enterDemo();
    } else {
      state = AuthSession.unauthenticated;
    }
  }

  Future<Result<AuthSession>> login(String email, String password) async {
    final r = await _repo.login(email, password);
    if (r is Ok<AuthSession>) state = r.value;
    return r;
  }

  void enterDemo() => state = _repo.enterDemo();

  Future<void> logout() async {
    await _repo.logout();
    state = AuthSession.unauthenticated;
  }
}

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthSession>((ref) {
  final demo = ref.watch(appConfigProvider).demoMode;
  return AuthController(ref.watch(authRepositoryProvider), demoMode: demo);
});
