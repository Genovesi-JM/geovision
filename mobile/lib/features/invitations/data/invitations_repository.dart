import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/errors/result.dart';
import '../../../core/networking/api_client.dart';
import '../domain/invitation.dart';

class InvitationsRepository {
  const InvitationsRepository(this._api);

  final ApiClient _api;

  Future<Result<InvitationPreview>> preview(String token) async {
    try {
      final response = await _api.raw.post(
        '/invitations/preview',
        data: {'token': token.trim()},
      );
      return Ok(InvitationPreview.fromJson(
          Map<String, dynamic>.from(response.data as Map)));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }

  Future<Result<InvitationDestination>> accept(String token) async {
    try {
      final response = await _api.raw.post(
        '/invitations/accept',
        data: {'token': token.trim()},
      );
      final body = Map<String, dynamic>.from(response.data as Map);
      final invitation =
          Map<String, dynamic>.from(body['invitation'] as Map? ?? const {});
      final destination = Map<String, dynamic>.from(
          invitation['destination'] as Map? ?? const {});
      return Ok(InvitationDestination.fromJson(destination));
    } catch (error) {
      return Err(_api.mapError(error));
    }
  }
}

final invitationsRepositoryProvider = Provider<InvitationsRepository>(
    (ref) => InvitationsRepository(ref.watch(apiClientProvider)));
