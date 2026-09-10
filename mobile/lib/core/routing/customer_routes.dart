/// Allowlisted customer navigation derived from backend-owned typed targets.
/// Arbitrary backend or invitation URLs are never opened by the app.
abstract final class CustomerRoutes {
  static final _safeId = RegExp(r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$');

  static String? forTarget(String type, String? id) {
    final normalizedType = type.trim().toUpperCase();
    final normalizedId = id?.trim();
    if (normalizedType == 'WORKSPACE' || normalizedType == 'INVITATION') {
      return '/home';
    }
    if (normalizedId == null || !_safeId.hasMatch(normalizedId)) return null;
    return switch (normalizedType) {
      'ASSET' => '/assets/$normalizedId',
      'ACTION' => '/actions/$normalizedId',
      'SERVICE' => '/services/$normalizedId',
      'ORDER' => '/services/orders/$normalizedId',
      'REPORT' => '/reports/$normalizedId',
      'SERVICE_RESULT' => '/work/$normalizedId',
      _ => null,
    };
  }

  /// Prefer the server-provided destination only when it exactly agrees with
  /// the invitation's typed target. Legacy paths are canonicalized.
  static String? forInvitation({
    required String kind,
    required String? targetId,
    required String? path,
  }) {
    final canonical = forTarget(kind, targetId);
    if (canonical == null) return null;
    final supplied = path?.trim();
    if (supplied == null || supplied.isEmpty) return canonical;
    if (Uri.tryParse(supplied) case final uri?
        when !uri.hasScheme &&
            uri.host.isEmpty &&
            uri.query.isEmpty &&
            uri.fragment.isEmpty) {
      final expected = <String>{canonical};
      final id = targetId?.trim();
      final legacy = switch (kind.trim().toLowerCase()) {
        'workspace' => '/portal',
        'asset' when id != null => '/sites/$id',
        'order' when id != null => '/orders/$id',
        'service_result' when id != null => '/work/$id',
        'report' when id != null => '/reports/$id',
        _ => null,
      };
      if (legacy != null) expected.add(legacy);
      if (expected.contains(uri.path)) return canonical;
    }
    return canonical;
  }
}
