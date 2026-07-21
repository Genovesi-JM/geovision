import 'package:equatable/equatable.dart';

/// Base type for all user-surfaceable failures. Repositories translate
/// low-level exceptions into these so the UI can render friendly states.
sealed class Failure extends Equatable {
  const Failure(this.message, {this.cause});
  final String message;
  final Object? cause;

  @override
  List<Object?> get props => [message];
}

class NetworkFailure extends Failure {
  const NetworkFailure({
    String message = 'No internet connection.',
    Object? cause,
  }) : super(message, cause: cause);
}

class TimeoutFailure extends Failure {
  const TimeoutFailure({
    String message = 'The request timed out.',
    Object? cause,
  }) : super(message, cause: cause);
}

class ServerFailure extends Failure {
  const ServerFailure(super.message, {this.statusCode, super.cause});
  final int? statusCode;

  @override
  List<Object?> get props => [message, statusCode];
}

class UnauthorizedFailure extends Failure {
  const UnauthorizedFailure({
    String message = 'Your session has expired.',
    Object? cause,
  }) : super(message, cause: cause);
}

class CacheFailure extends Failure {
  const CacheFailure({
    String message = 'No cached data available offline.',
    Object? cause,
  }) : super(message, cause: cause);
}

class ValidationFailure extends Failure {
  const ValidationFailure(super.message, {super.cause});
}

class UnknownFailure extends Failure {
  const UnknownFailure({
    String message = 'Something went wrong.',
    Object? cause,
  }) : super(message, cause: cause);
}
