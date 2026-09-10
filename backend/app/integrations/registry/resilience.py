"""Pure, bounded resilience decisions for registry-backed provider calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from enum import Enum
import math

from app.core.integration import (
    IntegrationError,
    IntegrationFailure,
    RetryPolicy,
    TimeoutPolicy,
)
from app.modules.integration_registry.domain import CircuitState


class TimeoutOperation(str, Enum):
    CONNECT = "connect"
    READ = "read"
    WRITE = "write"
    POOL = "pool"


def timeout_seconds(policy: TimeoutPolicy, operation: TimeoutOperation | str) -> float:
    """Select a finite positive timeout from the shared timeout policy."""

    try:
        selected = TimeoutOperation(operation)
    except ValueError as exc:
        raise ValueError("unsupported timeout operation") from exc
    value = {
        TimeoutOperation.CONNECT: policy.connect_seconds,
        TimeoutOperation.READ: policy.read_seconds,
        TimeoutOperation.WRITE: policy.write_seconds,
        TimeoutOperation.POOL: policy.pool_seconds,
    }[selected]
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError("integration timeout must be finite and positive")
    return value


class FailureDisposition(str, Enum):
    TERMINAL = "terminal"
    RETRYABLE = "retryable"


def failure_disposition(
    failure: IntegrationFailure | IntegrationError | BaseException,
) -> FailureDisposition:
    """Unknown exceptions are terminal until explicitly normalized."""

    if isinstance(failure, IntegrationFailure):
        retryable = failure.retryable
    elif isinstance(failure, IntegrationError):
        retryable = bool(failure.retryable)
    else:
        retryable = False
    return FailureDisposition.RETRYABLE if retryable else FailureDisposition.TERMINAL


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def parse_retry_after(
    value: str | None,
    *,
    now: datetime,
    maximum_seconds: float,
) -> float | None:
    """Parse HTTP Retry-After seconds/date without exceeding a caller bound."""

    now = _aware_utc(now, field_name="now")
    if not math.isfinite(maximum_seconds) or maximum_seconds < 0:
        raise ValueError("maximum_seconds must be finite and non-negative")
    if value is None:
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 128:
        return None
    try:
        seconds = float(candidate)
        if not math.isfinite(seconds):
            return None
    except ValueError:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        seconds = (parsed.astimezone(timezone.utc) - now).total_seconds()
    return min(max(seconds, 0.0), maximum_seconds)


class RetryReason(str, Enum):
    SCHEDULED = "scheduled"
    TERMINAL_FAILURE = "terminal_failure"
    UNSAFE_OPERATION = "unsafe_operation"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    delay_seconds: float | None
    reason: RetryReason

    def __post_init__(self) -> None:
        if self.should_retry != (self.delay_seconds is not None):
            raise ValueError("retry delay must exist exactly when a retry is scheduled")


def bounded_retry_decision(
    policy: RetryPolicy,
    *,
    attempts_made: int,
    failure: IntegrationFailure | IntegrationError,
    operation_is_idempotent: bool,
    idempotency_key: str | None = None,
    retry_after_header: str | None = None,
    now: datetime | None = None,
) -> RetryDecision:
    """Combine shared retry policy, safety, and a bounded Retry-After hint."""

    if attempts_made < 1:
        raise ValueError("attempts_made must be positive")
    if failure_disposition(failure) is FailureDisposition.TERMINAL:
        return RetryDecision(False, None, RetryReason.TERMINAL_FAILURE)
    has_idempotency_key = isinstance(idempotency_key, str) and bool(
        idempotency_key.strip()
    )
    if not operation_is_idempotent and not has_idempotency_key:
        return RetryDecision(False, None, RetryReason.UNSAFE_OPERATION)
    if attempts_made >= policy.max_attempts:
        return RetryDecision(False, None, RetryReason.ATTEMPTS_EXHAUSTED)

    current = _aware_utc(
        now or datetime.now(timezone.utc),
        field_name="now",
    )
    if any(
        isinstance(value, bool) or not math.isfinite(float(value))
        for value in (
            policy.initial_delay_seconds,
            policy.multiplier,
            policy.max_delay_seconds,
        )
    ):
        raise ValueError("retry policy values must be finite numbers")
    try:
        calculated = policy.initial_delay_seconds * (
            policy.multiplier ** (attempts_made - 1)
        )
    except OverflowError:
        calculated = policy.max_delay_seconds
    exponential = min(policy.max_delay_seconds, calculated)
    requested_values: list[float] = []
    retry_after_seconds = getattr(failure, "retry_after_seconds", None)
    if isinstance(retry_after_seconds, (int, float)) and not isinstance(
        retry_after_seconds, bool
    ):
        if math.isfinite(float(retry_after_seconds)):
            requested_values.append(max(0.0, float(retry_after_seconds)))
        elif retry_after_seconds > 0:
            requested_values.append(policy.max_delay_seconds)
    parsed_header = parse_retry_after(
        retry_after_header,
        now=current,
        maximum_seconds=policy.max_delay_seconds,
    )
    if parsed_header is not None:
        requested_values.append(parsed_header)
    delay = min(
        policy.max_delay_seconds,
        max([exponential, *requested_values]),
    )
    return RetryDecision(True, delay, RetryReason.SCHEDULED)


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    failure_threshold: int = 5
    open_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("circuit failure threshold must be positive")
        if not math.isfinite(self.open_seconds) or self.open_seconds <= 0:
            raise ValueError("circuit open duration must be finite and positive")


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_until: datetime | None = None
    probe_in_flight: bool = False

    def __post_init__(self) -> None:
        if self.consecutive_failures < 0:
            raise ValueError("circuit failure count must be non-negative")
        if self.opened_until is not None:
            _aware_utc(self.opened_until, field_name="opened_until")
        if self.state is CircuitState.CLOSED and (
            self.opened_until is not None or self.probe_in_flight
        ):
            raise ValueError("closed circuit cannot contain open/probe state")
        if self.state is CircuitState.OPEN and (
            self.opened_until is None or self.probe_in_flight
        ):
            raise ValueError("open circuit requires a deadline and no probe")
        if self.state is CircuitState.HALF_OPEN and self.opened_until is not None:
            raise ValueError("half-open circuit cannot retain an open deadline")


class CircuitGateReason(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN_PROBE = "half_open_probe"
    PROBE_IN_FLIGHT = "probe_in_flight"


@dataclass(frozen=True, slots=True)
class CircuitGate:
    allowed: bool
    probe: bool
    retry_after_seconds: float | None
    reason: CircuitGateReason
    next_snapshot: CircuitSnapshot


def circuit_gate(snapshot: CircuitSnapshot, *, now: datetime) -> CircuitGate:
    """Make an atomic-ready allow/block/probe decision from persisted state."""

    current = _aware_utc(now, field_name="now")
    if snapshot.state is CircuitState.CLOSED:
        return CircuitGate(True, False, None, CircuitGateReason.CLOSED, snapshot)
    if snapshot.state is CircuitState.OPEN:
        assert snapshot.opened_until is not None
        opened_until = snapshot.opened_until.astimezone(timezone.utc)
        if current < opened_until:
            return CircuitGate(
                False,
                False,
                max(0.0, (opened_until - current).total_seconds()),
                CircuitGateReason.OPEN,
                snapshot,
            )
        probe_snapshot = CircuitSnapshot(
            state=CircuitState.HALF_OPEN,
            consecutive_failures=snapshot.consecutive_failures,
            probe_in_flight=True,
        )
        return CircuitGate(
            True,
            True,
            None,
            CircuitGateReason.HALF_OPEN_PROBE,
            probe_snapshot,
        )
    if snapshot.probe_in_flight:
        return CircuitGate(
            False,
            False,
            None,
            CircuitGateReason.PROBE_IN_FLIGHT,
            snapshot,
        )
    probe_snapshot = CircuitSnapshot(
        state=CircuitState.HALF_OPEN,
        consecutive_failures=snapshot.consecutive_failures,
        probe_in_flight=True,
    )
    return CircuitGate(
        True,
        True,
        None,
        CircuitGateReason.HALF_OPEN_PROBE,
        probe_snapshot,
    )


def close_circuit() -> CircuitSnapshot:
    return CircuitSnapshot()


def record_circuit_success(snapshot: CircuitSnapshot) -> CircuitSnapshot:
    del snapshot
    return close_circuit()


def failure_counts_toward_circuit(
    failure: IntegrationFailure | IntegrationError,
) -> bool:
    code = failure.code.strip().lower()
    return failure_disposition(
        failure
    ) is FailureDisposition.RETRYABLE and code not in {
        "rate_limited",
        "not_configured",
        "authentication_failed",
    }


def record_circuit_failure(
    snapshot: CircuitSnapshot,
    failure: IntegrationFailure | IntegrationError,
    *,
    now: datetime,
    policy: CircuitBreakerPolicy,
) -> CircuitSnapshot:
    """Record only transient availability failures; rate limits use their own gate."""

    current = _aware_utc(now, field_name="now")
    if not failure_counts_toward_circuit(failure):
        return close_circuit() if snapshot.state is CircuitState.HALF_OPEN else snapshot
    failures = snapshot.consecutive_failures + 1
    if snapshot.state is CircuitState.HALF_OPEN or failures >= policy.failure_threshold:
        return CircuitSnapshot(
            state=CircuitState.OPEN,
            consecutive_failures=failures,
            opened_until=current + timedelta(seconds=policy.open_seconds),
        )
    return CircuitSnapshot(
        state=CircuitState.CLOSED,
        consecutive_failures=failures,
    )


@dataclass(frozen=True, slots=True)
class RateLimitGate:
    allowed: bool
    retry_after_seconds: float | None


def rate_limit_gate(
    rate_limited_until: datetime | None,
    *,
    now: datetime,
) -> RateLimitGate:
    """Block calls until the persisted provider rate-limit deadline."""

    current = _aware_utc(now, field_name="now")
    if rate_limited_until is None:
        return RateLimitGate(True, None)
    deadline = _aware_utc(rate_limited_until, field_name="rate_limited_until")
    if deadline <= current:
        return RateLimitGate(True, None)
    return RateLimitGate(False, (deadline - current).total_seconds())


__all__ = [
    "CircuitBreakerPolicy",
    "CircuitGate",
    "CircuitGateReason",
    "CircuitSnapshot",
    "CircuitState",
    "FailureDisposition",
    "RateLimitGate",
    "RetryDecision",
    "RetryReason",
    "TimeoutOperation",
    "bounded_retry_decision",
    "circuit_gate",
    "close_circuit",
    "failure_counts_toward_circuit",
    "failure_disposition",
    "parse_retry_after",
    "rate_limit_gate",
    "record_circuit_failure",
    "record_circuit_success",
    "timeout_seconds",
]
