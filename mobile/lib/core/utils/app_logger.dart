import 'dart:developer' as dev;

/// Minimal structured logger. Never logs tokens, passwords or PII.
/// Wraps dart:developer so crash-reporting adapters can hook in later.
class AppLogger {
  const AppLogger(this._tag);
  final String _tag;

  void info(String message) => dev.log(message, name: 'GV/$_tag');

  void warn(String message) => dev.log('WARN $message', name: 'GV/$_tag');

  void error(String message, [Object? error, StackTrace? stack]) => dev
      .log('ERROR $message', name: 'GV/$_tag', error: error, stackTrace: stack);
}
