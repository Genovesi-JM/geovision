import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/providers.dart';
import '../../../core/networking/api_client.dart';

class GaiaMessage {
  const GaiaMessage({required this.role, required this.content});
  final String role;
  final String content;

  Map<String, String> toJson() => {'role': role, 'content': content};
}

class GaiaRepository {
  const GaiaRepository(this._api);
  final ApiClient _api;

  Future<String> send(List<GaiaMessage> messages, {String? language}) async {
    final response = await _api.raw.post<Map<String, dynamic>>(
      '/ai/chat',
      data: {
        'messages': messages.map((message) => message.toJson()).toList(),
        'page': '/mobile/assistant',
        'page_title': 'GeoVision mobile application',
        'sector': 'Geral',
        'page_text':
            'Mobile customer app. Preferred language: ${language ?? 'pt'}. '
                'The user can access sites, alerts, work, devices, reports, guides, store and account.',
      },
    );
    final reply = response.data?['reply']?.toString().trim();
    if (reply == null || reply.isEmpty) {
      throw StateError('The assistant returned an empty response.');
    }
    return reply;
  }
}

final gaiaRepositoryProvider = Provider<GaiaRepository>(
  (ref) => GaiaRepository(ref.watch(apiClientProvider)),
);
