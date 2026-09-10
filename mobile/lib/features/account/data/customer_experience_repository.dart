import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/config/app_config.dart';
import '../../../core/errors/failures.dart';
import '../../../core/networking/api_client.dart';
import '../../../core/storage/local_store.dart';
import '../domain/customer_experience.dart';

class CustomerExperienceException implements Exception {
  const CustomerExperienceException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;
  @override
  String toString() => message;
}

class CustomerExperienceRepository {
  CustomerExperienceRepository(this._api, this._store, this._config);

  final ApiClient _api;
  final LocalStore _store;
  final AppConfig _config;
  static const _selectionKey = 'customer_workspace_selection';

  Future<CustomerExperience> load() async {
    if (_config.demoMode) {
      final selected = _savedWorkspaceId();
      return _selectDemo(selected);
    }
    final selected = _savedWorkspaceId();
    _api.selectWorkspace(selected);
    try {
      return await _fetchAndRemember();
    } on CustomerExperienceException catch (error) {
      if (selected == null ||
          (error.statusCode != 403 && error.statusCode != 404)) {
        rethrow;
      }
      _api.selectWorkspace(null);
      await _store.remove(_selectionKey);
      return _fetchAndRemember();
    }
  }

  Future<CustomerExperience> select(String workspaceId) async {
    final previous = _api.workspaceId;
    try {
      _api.selectWorkspace(workspaceId);
      if (_config.demoMode) {
        final experience = _selectDemo(workspaceId);
        await _remember(experience.activeWorkspaceId);
        return experience;
      }
      final experience = await _fetchAndRemember();
      if (experience.activeWorkspaceId != workspaceId ||
          !experience.workspaces
              .any((workspace) => workspace.id == workspaceId)) {
        throw const CustomerExperienceException(
            'The selected workspace is not available.');
      }
      return experience;
    } catch (error) {
      _api.selectWorkspace(previous);
      if (error is CustomerExperienceException) rethrow;
      throw CustomerExperienceException(_api.mapError(error).message);
    }
  }

  Future<CustomerExperience> _fetchAndRemember() async {
    try {
      final response = await _api.raw.get('/mobile/experience');
      final experience = CustomerExperience.fromJson(
          Map<String, dynamic>.from(response.data as Map));
      _api.selectWorkspace(experience.activeWorkspaceId);
      await _remember(experience.activeWorkspaceId);
      return experience;
    } catch (error) {
      final failure = _api.mapError(error);
      throw CustomerExperienceException(
        failure.message,
        statusCode: failure is ServerFailure ? failure.statusCode : null,
      );
    }
  }

  CustomerExperience _selectDemo(String? workspaceId) {
    final selected = CustomerExperience.demo.workspaces
            .any((workspace) => workspace.id == workspaceId)
        ? workspaceId
        : CustomerExperience.demo.activeWorkspaceId;
    _api.selectWorkspace(selected);
    return CustomerExperience(
      activeWorkspaceId: selected,
      activeOrganizationId: CustomerExperience.demo.activeOrganizationId,
      permissions: CustomerExperience.demo.permissions,
      capabilities: CustomerExperience.demo.capabilities,
      workspaces: CustomerExperience.demo.workspaces,
    );
  }

  String? _savedWorkspaceId() {
    final data = _store.readJson(_selectionKey)?.data;
    return data is Map ? data['workspace_id']?.toString() : null;
  }

  Future<void> _remember(String? workspaceId) async {
    if (workspaceId == null) {
      await _store.remove(_selectionKey);
    } else {
      await _store.writeJson(_selectionKey, {'workspace_id': workspaceId});
    }
  }
}

final customerExperienceRepositoryProvider =
    Provider<CustomerExperienceRepository>(
        (ref) => CustomerExperienceRepository(
              ref.watch(apiClientProvider),
              ref.watch(localStoreProvider),
              ref.watch(appConfigProvider),
            ));

class CustomerExperienceController extends AsyncNotifier<CustomerExperience> {
  @override
  Future<CustomerExperience> build() =>
      ref.watch(customerExperienceRepositoryProvider).load();

  Future<bool> switchWorkspace(String workspaceId) async {
    if (state.valueOrNull?.activeWorkspaceId == workspaceId) return true;
    final previous = state;
    state = const AsyncLoading();
    try {
      final experience = await ref
          .read(customerExperienceRepositoryProvider)
          .select(workspaceId);
      state = AsyncData(experience);
      return true;
    } catch (error, stackTrace) {
      // Explicit switching is transactional from the UI's point of view: the
      // repository restores the header and the controller restores the
      // previously rendered workspace. The caller can surface the failure.
      state = previous.hasValue ? previous : AsyncError(error, stackTrace);
      return false;
    }
  }

  Future<void> reload() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(
        () => ref.read(customerExperienceRepositoryProvider).load());
  }
}

final customerExperienceProvider =
    AsyncNotifierProvider<CustomerExperienceController, CustomerExperience>(
        CustomerExperienceController.new);
