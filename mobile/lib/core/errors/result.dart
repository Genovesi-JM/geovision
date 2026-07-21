import 'failures.dart';

/// A tiny Either-like Result to avoid throwing across repository boundaries.
sealed class Result<T> {
  const Result();

  R when<R>({
    required R Function(T value) ok,
    required R Function(Failure failure) err,
  }) {
    final self = this;
    if (self is Ok<T>) return ok(self.value);
    return err((self as Err<T>).failure);
  }

  T? get valueOrNull => this is Ok<T> ? (this as Ok<T>).value : null;
  bool get isOk => this is Ok<T>;
}

class Ok<T> extends Result<T> {
  const Ok(this.value);
  final T value;
}

class Err<T> extends Result<T> {
  const Err(this.failure);
  final Failure failure;
}
