import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../config/api_config.dart';

class ApiClient {
  ApiClient._();

  static final ApiClient instance = ApiClient._();

  static const _tokenKey = 'gv_token';

  String? _token;

  Future<void> _ensureToken() async {
    final has = await hasToken();
    if (!has) {
      throw Exception(
        'Nenhum token de sessão encontrado. Inicie sessão para continuar.',
      );
    }
  }

  Future<bool> hasToken() async {
    if (_token != null && _token!.isNotEmpty) {
      return true;
    }
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_tokenKey);
    if (stored != null && stored.isNotEmpty) {
      _token = stored;
      return true;
    }
    return false;
  }

  Future<void> saveToken(String token) async {
    _token = token;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  Future<Map<String, dynamic>> getJson(String path) async {
    await _ensureToken();
    final uri = Uri.parse('${ApiConfig.baseUrl}$path');
    final res = await http.get(uri, headers: _authHeaders());

    if (res.statusCode == 401) {
      await _handleUnauthorized();
      return getJson(path);
    }

    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('Erro ${res.statusCode}: ${res.body}');
    }

    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Future<List<dynamic>> getJsonList(String path) async {
    await _ensureToken();
    final uri = Uri.parse('${ApiConfig.baseUrl}$path');
    final res = await http.get(uri, headers: _authHeaders());

    if (res.statusCode == 401) {
      await _handleUnauthorized();
      return getJsonList(path);
    }

    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('Erro ${res.statusCode}: ${res.body}');
    }

    final body = jsonDecode(res.body);
    if (body is List) return body;
    throw Exception('Resposta inesperada da API (esperava lista).');
  }

  Future<Map<String, dynamic>> postJson(
    String path,
    Map<String, dynamic> body,
  ) async {
    await _ensureToken();
    final uri = Uri.parse('${ApiConfig.baseUrl}$path');
    final res = await http.post(
      uri,
      headers: _authHeaders(),
      body: jsonEncode(body),
    );

    if (res.statusCode == 401) {
      await _handleUnauthorized();
      return postJson(path, body);
    }

    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw Exception('Erro ${res.statusCode}: ${res.body}');
    }

    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  Map<String, String> _authHeaders() {
    return {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
      if (_token != null) 'Authorization': 'Bearer $_token',
    };
  }

  Future<void> _handleUnauthorized() async {
    await clearToken();
    throw Exception('Não autorizado. Inicie sessão novamente.');
  }

  Future<void> clearToken() async {
    _token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}
