"""Contract tests for the Phase 32 integration-registry policy adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import UUID

import pytest

from app.core.integration import (
    IntegrationAuthenticationError,
    IntegrationFailure,
    IntegrationRateLimitError,
    IntegrationTimeoutError,
    RetryPolicy,
    TimeoutPolicy,
)
from app.integrations.registry import (
    AzureAppConfigurationFeatureFlagEvaluator,
    AzureKeyVaultSecretStore,
    CircuitBreakerPolicy,
    CircuitGateReason,
    CircuitSnapshot,
    CircuitState,
    DeterministicFeatureFlagEvaluator,
    FailureDisposition,
    FeatureFlagEvaluator,
    FeatureFlagHealthState,
    FeatureFlagTarget,
    InMemorySecretStore,
    InvalidSecretReference,
    NullFeatureFlagEvaluator,
    NullSecretStore,
    RetryReason,
    SecretNotFound,
    SecretStore,
    SecretStoreHealthState,
    SecretStoreUnavailable,
    bounded_retry_decision,
    circuit_gate,
    failure_counts_toward_circuit,
    failure_disposition,
    parse_key_vault_secret_reference,
    parse_retry_after,
    rate_limit_gate,
    record_circuit_failure,
    record_circuit_success,
    timeout_seconds,
)
from app.modules.integration_registry.domain import CircuitState as DomainCircuitState
from app.modules.integration_registry.domain import required_sync_capability


ORG_ID = UUID("74d739f3-dd4e-45ec-9f61-42629ebb5206")
WORKSPACE_ID = UUID("a7912c43-244a-4282-89db-dfdd12b1fd37")
USER_ID = UUID("2fcc7e3e-f820-4800-a348-c86b89f671a1")
OTHER_USER_ID = UUID("a8ea9e5a-2f05-4e12-b10b-a88cb07a3fdd")
FLAG = "geovision.integrations.asset_management"
NOW = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)


@dataclass
class ManualClock:
    value: datetime = NOW

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: float) -> None:
        self.value += timedelta(**kwargs)


def _target(*, user_id: UUID | None = USER_ID) -> FeatureFlagTarget:
    return FeatureFlagTarget(
        organization_id=ORG_ID,
        workspace_id=WORKSPACE_ID,
        user_id=user_id,
    )


@pytest.mark.parametrize(
    ("family", "direction", "operation", "capability"),
    [
        ("construction", "inbound", "synchronize_project", "project.read"),
        ("construction", "outbound", "synchronize_project", "project.write"),
        ("asset_management", "inbound", "synchronize_asset", "asset.read"),
        ("asset_management", "outbound", "synchronize_asset", "asset.write"),
        ("gis", "inbound", "query_layers", "layer.read"),
        ("maritime", "inbound", "operational_context", "context.read"),
    ],
)
def test_normalized_sync_operations_map_to_family_capabilities(
    family: str,
    direction: str,
    operation: str,
    capability: str,
) -> None:
    assert required_sync_capability(family, direction, operation) == capability


@pytest.mark.parametrize(
    ("family", "direction", "operation"),
    [
        ("gis", "outbound", "query_layers"),
        ("maritime", "outbound", "operational_context"),
        ("construction", "inbound", "vendor_specific_call"),
    ],
)
def test_unregistered_sync_patterns_fail_closed(
    family: str,
    direction: str,
    operation: str,
) -> None:
    with pytest.raises(ValueError, match="not registered"):
        required_sync_capability(family, direction, operation)


def _azure_flag(
    *,
    enabled: bool = True,
    users: list[str] | None = None,
    groups: list[dict[str, Any]] | None = None,
    excluded_users: list[str] | None = None,
    excluded_groups: list[str] | None = None,
    default_percentage: float = 0,
) -> dict[str, Any]:
    audience = {
        "Users": users or [],
        "Groups": groups or [],
        "DefaultRolloutPercentage": default_percentage,
        "Exclusion": {
            "Users": excluded_users or [],
            "Groups": excluded_groups or [],
        },
    }
    return {
        "id": FLAG,
        "enabled": enabled,
        "conditions": {
            "client_filters": [
                {
                    "name": "Microsoft.Targeting",
                    "parameters": {"Audience": audience},
                }
            ]
        },
    }


def test_null_feature_flags_are_protocol_compatible_and_fail_closed():
    evaluator = NullFeatureFlagEvaluator()

    assert isinstance(evaluator, FeatureFlagEvaluator)
    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    assert evaluator.health().state is FeatureFlagHealthState.UNAVAILABLE


def test_feature_target_requires_uuid_values_and_exposes_only_uuid_keys():
    target = _target()

    assert target.precedence_keys() == (
        f"user:{USER_ID}",
        f"workspace:{WORKSPACE_ID}",
        f"organization:{ORG_ID}",
    )
    with pytest.raises(TypeError, match="must be a UUID"):
        FeatureFlagTarget(organization_id=str(ORG_ID))  # type: ignore[arg-type]


def test_deterministic_evaluator_uses_most_specific_rule_and_never_grants_access():
    evaluator = DeterministicFeatureFlagEvaluator(
        {FLAG: False},
        target_decisions={
            (FLAG, f"organization:{ORG_ID}"): True,
            (FLAG, f"workspace:{WORKSPACE_ID}"): False,
            (FLAG, f"user:{USER_ID}"): True,
        },
    )

    assert evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=False,
        entitled=True,
    )
    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=False,
    )


@pytest.mark.parametrize(
    "name",
    [
        "unrelated.flag",
        "geovision.integrations.client_secret",
        "geovision.integrations.api-token",
        "GEOVISION.integrations.asset_management",
    ],
)
def test_deterministic_evaluator_rejects_out_of_scope_or_secret_like_flags(name: str):
    with pytest.raises(ValueError, match="allowed GeoVision"):
        DeterministicFeatureFlagEvaluator({name: True})


def test_azure_cold_start_failure_is_fail_closed_and_does_not_leak_error():
    leaked = "https://vault.vault.azure.net/secrets/client-secret bearer top-secret"

    def loader() -> dict[str, object]:
        raise RuntimeError(leaked)

    evaluator = AzureAppConfigurationFeatureFlagEvaluator(loader, clock=lambda: NOW)

    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    health = evaluator.health()
    assert health.state is FeatureFlagHealthState.UNAVAILABLE
    assert health.reason_code == "feature_flag_cold_start_failed"
    assert leaked not in repr(evaluator)
    assert leaked not in repr(health)


def test_azure_loader_refresh_is_bounded_and_accepts_raw_json_keys():
    calls = 0

    def loader() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {f".appconfig.featureflag/{FLAG}": json.dumps(_azure_flag())}

    clock = ManualClock()
    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        loader,
        refresh_interval=timedelta(minutes=5),
        max_staleness=timedelta(hours=1),
        clock=clock,
    )

    for _ in range(3):
        assert not evaluator.allows_rollout(
            FLAG,
            target=_target(),
            authorized=True,
            entitled=True,
        )
    assert calls == 1
    clock.advance(minutes=5)
    evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    assert calls == 2


def test_azure_accepts_official_provider_nested_feature_management_shape():
    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {
            "feature_management": {
                "feature_flags": {FLAG: {"id": FLAG, "enabled": True, "conditions": {}}}
            }
        },
        clock=lambda: NOW,
    )

    assert evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )


def test_azure_accepts_standard_feature_flag_list_and_all_without_filters_is_off():
    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {
            "feature_management": {
                "feature_flags": [
                    {
                        "id": FLAG,
                        "enabled": True,
                        "conditions": {
                            "requirement_type": "All",
                            "client_filters": [],
                        },
                    }
                ]
            }
        },
        clock=lambda: NOW,
    )

    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )


def test_azure_last_known_snapshot_is_degraded_then_expires():
    clock = ManualClock()
    available = True

    def loader() -> dict[str, object]:
        if not available:
            raise RuntimeError("Authorization: Bearer should-never-escape")
        return {FLAG: {"id": FLAG, "enabled": True, "conditions": {}}}

    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        loader,
        refresh_interval=timedelta(minutes=5),
        max_staleness=timedelta(minutes=30),
        clock=clock,
    )
    assert evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )

    available = False
    clock.advance(minutes=5)
    assert evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    assert evaluator.health().state is FeatureFlagHealthState.DEGRADED
    assert evaluator.health().stale is True

    clock.advance(minutes=26)
    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    assert evaluator.health().state is FeatureFlagHealthState.EXPIRED


def test_azure_health_reports_an_overdue_unrefreshed_snapshot_as_stale():
    clock = ManualClock()
    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {FLAG: {"id": FLAG, "enabled": True}},
        refresh_interval=timedelta(minutes=5),
        max_staleness=timedelta(minutes=30),
        clock=clock,
    )
    assert evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    clock.advance(minutes=6)

    health = evaluator.health()
    assert health.state is FeatureFlagHealthState.DEGRADED
    assert health.reason_code == "feature_flag_snapshot_stale"


def test_azure_targeting_exclusions_take_precedence_over_users_and_groups():
    definition = _azure_flag(
        users=[f"user:{USER_ID}"],
        groups=[
            {
                "Name": f"workspace:{WORKSPACE_ID}",
                "RolloutPercentage": 100,
            }
        ],
        excluded_groups=[f"organization:{ORG_ID}"],
        default_percentage=100,
    )
    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {FLAG: definition},
        clock=lambda: NOW,
    )

    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )


def test_azure_targeting_user_group_and_default_rollout_are_deterministic():
    included_user = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {FLAG: _azure_flag(users=[f"user:{USER_ID}"])},
        clock=lambda: NOW,
    )
    included_group = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {
            FLAG: _azure_flag(
                groups=[
                    {
                        "Name": f"organization:{ORG_ID}",
                        "RolloutPercentage": 100,
                    }
                ]
            )
        },
        clock=lambda: NOW,
    )
    default_all = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: {FLAG: _azure_flag(default_percentage=100)},
        clock=lambda: NOW,
    )

    assert included_user.allows_rollout(
        FLAG, target=_target(), authorized=True, entitled=True
    )
    assert included_group.allows_rollout(
        FLAG,
        target=_target(user_id=OTHER_USER_ID),
        authorized=True,
        entitled=True,
    )
    assert default_all.allows_rollout(
        FLAG,
        target=_target(user_id=None),
        authorized=True,
        entitled=True,
    )


@pytest.mark.parametrize(
    "snapshot",
    [
        {"outside.namespace": {"enabled": True}},
        {"geovision.integrations.api_key": {"enabled": True}},
        {FLAG: {"enabled": "yes"}},
        {FLAG: {"enabled": True, "client_secret": "do-not-store"}},
        {FLAG: {"enabled": True, "description": "token=do-not-store"}},
        {FLAG: {"enabled": True, "description": "x" * 20_000}},
        {
            FLAG: _azure_flag(users=["user:not-a-uuid"]),
        },
        {
            FLAG: {
                "id": FLAG,
                "enabled": True,
                "conditions": {
                    "client_filters": [{"name": "Custom.Filter", "parameters": {}}]
                },
            }
        },
    ],
)
def test_azure_invalid_or_secret_like_configuration_fails_closed(snapshot):
    evaluator = AzureAppConfigurationFeatureFlagEvaluator(
        lambda: snapshot,
        clock=lambda: NOW,
    )

    assert not evaluator.allows_rollout(
        FLAG,
        target=_target(),
        authorized=True,
        entitled=True,
    )
    assert evaluator.health().reason_code == "feature_flag_cold_start_failed"


def test_azure_does_not_load_flags_when_authorization_or_entitlement_is_absent():
    calls = 0

    def loader() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {FLAG: _azure_flag(default_percentage=100)}

    evaluator = AzureAppConfigurationFeatureFlagEvaluator(loader, clock=lambda: NOW)
    assert not evaluator.allows_rollout(
        FLAG, target=_target(), authorized=False, entitled=True
    )
    assert not evaluator.allows_rollout(
        FLAG, target=_target(), authorized=True, entitled=False
    )
    assert calls == 0


def test_key_vault_reference_parser_accepts_only_canonical_optional_version_uri():
    unversioned = parse_key_vault_secret_reference(
        "https://geo-vault.vault.azure.net/secrets/provider-client"
    )
    versioned = parse_key_vault_secret_reference(
        "https://geo-vault.vault.azure.net/secrets/provider-client/abc123"
    )

    assert unversioned.vault_url == "https://geo-vault.vault.azure.net"
    assert unversioned.secret_name == "provider-client"
    assert unversioned.version is None
    assert versioned.version == "abc123"
    assert "geo-vault" not in repr(unversioned)
    assert "provider-client" not in str(versioned)


@pytest.mark.parametrize(
    "uri",
    [
        "http://geo-vault.vault.azure.net/secrets/provider-client",
        "https://geo-vault.example.com/secrets/provider-client",
        "https://user:pass@geo-vault.vault.azure.net/secrets/provider-client",
        "https://geo-vault.vault.azure.net:443/secrets/provider-client",
        "https://geo-vault.vault.azure.net/keys/provider-client",
        "https://geo-vault.vault.azure.net/secrets/provider%2Dclient",
        "https://geo-vault.vault.azure.net/secrets/provider-client/",
        "https://geo-vault.vault.azure.net/secrets/provider-client?v=1",
        "https://geo-vault.vault.azure.net/secrets/provider-client#fragment",
        " https://geo-vault.vault.azure.net/secrets/provider-client",
    ],
)
def test_key_vault_reference_parser_rejects_noncanonical_uri_without_echo(uri: str):
    with pytest.raises(InvalidSecretReference) as error:
        parse_key_vault_secret_reference(uri)
    assert uri not in str(error.value)


def test_null_and_memory_secret_stores_are_protocol_compatible_and_redacted():
    uri = "https://geo-vault.vault.azure.net/secrets/provider-client/abc123"
    secret = "very-sensitive-provider-secret"
    null = NullSecretStore()
    memory = InMemorySecretStore({uri: secret})

    assert isinstance(null, SecretStore)
    assert isinstance(memory, SecretStore)
    with pytest.raises(SecretStoreUnavailable, match="not configured"):
        null.resolve(uri)
    resolved = memory.resolve(uri)
    assert resolved.reveal() == secret
    assert secret not in repr(resolved)
    assert uri not in repr(memory)
    assert memory.health().state is SecretStoreHealthState.HEALTHY
    with pytest.raises(SecretNotFound, match="not found") as error:
        memory.resolve("https://geo-vault.vault.azure.net/secrets/missing")
    assert "missing" not in str(error.value)


def test_explicit_secret_reference_is_revalidated_before_client_use():
    from app.integrations.registry import KeyVaultSecretReference

    forged = KeyVaultSecretReference(
        vault_url="http://metadata.internal",
        secret_name="provider-client",
    )
    calls = 0

    def factory(vault_url: str):
        nonlocal calls
        del vault_url
        calls += 1
        return FakeSecretClient("unused")

    store = AzureKeyVaultSecretStore(factory)
    with pytest.raises(InvalidSecretReference):
        store.resolve(forged)
    assert calls == 0


class FakeSecretClient:
    def __init__(self, value: str | None, *, error: Exception | None = None) -> None:
        self.value = value
        self.error = error
        self.calls: list[tuple[str, str | None]] = []

    def get_secret(self, name: str, version: str | None = None, **kwargs: Any):
        del kwargs
        self.calls.append((name, version))
        if self.error is not None:
            raise self.error
        return self


def test_azure_secret_store_uses_injected_client_contract_and_redacts_public_state():
    uri = "https://geo-vault.vault.azure.net/secrets/provider-client/abc123"
    secret = "azure-returned-secret"
    client = FakeSecretClient(secret)
    vaults: list[str] = []

    def factory(vault_url: str) -> FakeSecretClient:
        vaults.append(vault_url)
        return client

    store = AzureKeyVaultSecretStore(factory)
    assert store.health().state is SecretStoreHealthState.CONFIGURED
    assert store.resolve(uri).reveal() == secret
    assert vaults == ["https://geo-vault.vault.azure.net"]
    assert client.calls == [("provider-client", "abc123")]
    assert store.health().state is SecretStoreHealthState.HEALTHY
    combined = f"{store!r} {store.health()!r}"
    assert secret not in combined
    assert uri not in combined
    assert "provider-client" not in combined


def test_azure_secret_store_sanitizes_client_errors_and_invalid_refs_never_call_factory():
    leaked = "Bearer top-secret https://geo-vault.vault.azure.net/secrets/private"
    client = FakeSecretClient(None, error=RuntimeError(leaked))
    calls = 0

    def factory(vault_url: str) -> FakeSecretClient:
        nonlocal calls
        del vault_url
        calls += 1
        return client

    store = AzureKeyVaultSecretStore(factory)
    with pytest.raises(InvalidSecretReference):
        store.resolve("http://geo-vault.vault.azure.net/secrets/private")
    assert calls == 0
    with pytest.raises(SecretStoreUnavailable) as error:
        store.resolve("https://geo-vault.vault.azure.net/secrets/private")
    assert calls == 1
    assert leaked not in str(error.value)
    assert store.health().state is SecretStoreHealthState.DEGRADED


def test_timeout_selection_reuses_shared_policy_and_rejects_nonfinite_values():
    policy = TimeoutPolicy(
        connect_seconds=2,
        read_seconds=11,
        write_seconds=17,
        pool_seconds=3,
    )

    assert timeout_seconds(policy, "connect") == 2
    assert timeout_seconds(policy, "read") == 11
    assert timeout_seconds(policy, "write") == 17
    assert timeout_seconds(policy, "pool") == 3
    with pytest.raises(ValueError, match="unsupported"):
        timeout_seconds(policy, "delete")
    with pytest.raises(ValueError, match="finite"):
        timeout_seconds(TimeoutPolicy(read_seconds=float("inf")), "read")


def test_failure_disposition_defaults_unknown_errors_to_terminal():
    retryable = IntegrationTimeoutError(
        provider="test",
        operation="read",
        message="timed out",
    )
    terminal = IntegrationAuthenticationError(
        provider="test",
        operation="read",
        message="authentication failed",
    )

    assert failure_disposition(retryable) is FailureDisposition.RETRYABLE
    assert failure_disposition(terminal) is FailureDisposition.TERMINAL
    assert failure_disposition(RuntimeError("unknown")) is FailureDisposition.TERMINAL


def test_retry_after_supports_seconds_and_http_date_with_strict_bound():
    later = NOW + timedelta(seconds=90)
    http_date = later.strftime("%a, %d %b %Y %H:%M:%S GMT")

    assert parse_retry_after("12.5", now=NOW, maximum_seconds=60) == 12.5
    assert parse_retry_after("999", now=NOW, maximum_seconds=60) == 60
    assert parse_retry_after(http_date, now=NOW, maximum_seconds=120) == 90
    assert parse_retry_after("not-a-date", now=NOW, maximum_seconds=60) is None
    assert parse_retry_after("nan", now=NOW, maximum_seconds=60) is None


def test_retry_decision_is_bounded_honors_retry_after_and_requires_write_idempotency():
    policy = RetryPolicy(
        max_attempts=4,
        initial_delay_seconds=2,
        multiplier=2,
        max_delay_seconds=20,
    )
    failure = IntegrationFailure(
        code="timeout",
        message="provider timeout",
        retryable=True,
        retry_after_seconds=7,
    )

    unsafe = bounded_retry_decision(
        policy,
        attempts_made=2,
        failure=failure,
        operation_is_idempotent=False,
        now=NOW,
    )
    scheduled = bounded_retry_decision(
        policy,
        attempts_made=2,
        failure=failure,
        operation_is_idempotent=False,
        idempotency_key="sync:123",
        retry_after_header="200",
        now=NOW,
    )

    assert unsafe.reason is RetryReason.UNSAFE_OPERATION
    assert not unsafe.should_retry
    assert scheduled.reason is RetryReason.SCHEDULED
    assert scheduled.delay_seconds == 20


def test_retry_decision_stops_terminal_and_exhausted_failures():
    policy = RetryPolicy(max_attempts=2)
    terminal = IntegrationFailure(
        code="invalid_request",
        message="invalid",
        retryable=False,
    )
    retryable = IntegrationFailure(code="timeout", message="timeout", retryable=True)

    assert (
        bounded_retry_decision(
            policy,
            attempts_made=1,
            failure=terminal,
            operation_is_idempotent=True,
            now=NOW,
        ).reason
        is RetryReason.TERMINAL_FAILURE
    )
    assert (
        bounded_retry_decision(
            policy,
            attempts_made=2,
            failure=retryable,
            operation_is_idempotent=True,
            now=NOW,
        ).reason
        is RetryReason.ATTEMPTS_EXHAUSTED
    )


def test_circuit_opens_blocks_allows_one_half_open_probe_and_closes_on_success():
    assert CircuitState is DomainCircuitState
    policy = CircuitBreakerPolicy(failure_threshold=2, open_seconds=60)
    failure = IntegrationFailure(code="timeout", message="timeout", retryable=True)
    snapshot = record_circuit_failure(
        CircuitSnapshot(), failure, now=NOW, policy=policy
    )
    assert snapshot.state is CircuitState.CLOSED
    snapshot = record_circuit_failure(snapshot, failure, now=NOW, policy=policy)
    assert snapshot.state is CircuitState.OPEN

    blocked = circuit_gate(snapshot, now=NOW + timedelta(seconds=30))
    assert not blocked.allowed
    assert blocked.reason is CircuitGateReason.OPEN
    assert blocked.retry_after_seconds == 30

    probe = circuit_gate(snapshot, now=NOW + timedelta(seconds=60))
    assert probe.allowed and probe.probe
    assert probe.next_snapshot.state is CircuitState.HALF_OPEN
    competing = circuit_gate(probe.next_snapshot, now=NOW + timedelta(seconds=61))
    assert not competing.allowed
    assert competing.reason is CircuitGateReason.PROBE_IN_FLIGHT
    assert record_circuit_success(probe.next_snapshot) == CircuitSnapshot()


def test_half_open_retryable_failure_reopens_but_rate_limit_does_not_trip_circuit():
    policy = CircuitBreakerPolicy(failure_threshold=3, open_seconds=45)
    half_open = CircuitSnapshot(
        state=CircuitState.HALF_OPEN,
        consecutive_failures=3,
        probe_in_flight=True,
    )
    timeout = IntegrationFailure(code="timeout", message="timeout", retryable=True)
    limited = IntegrationRateLimitError(
        provider="test",
        operation="read",
        message="limited",
        retry_after_seconds=30,
    )

    reopened = record_circuit_failure(half_open, timeout, now=NOW, policy=policy)
    assert reopened.state is CircuitState.OPEN
    assert reopened.opened_until == NOW + timedelta(seconds=45)
    assert not failure_counts_toward_circuit(limited)
    assert (
        record_circuit_failure(
            half_open,
            limited,
            now=NOW,
            policy=policy,
        )
        == CircuitSnapshot()
    )


def test_rate_limit_gate_blocks_only_until_aware_deadline():
    blocked = rate_limit_gate(NOW + timedelta(seconds=25), now=NOW)
    released = rate_limit_gate(NOW, now=NOW)

    assert not blocked.allowed
    assert blocked.retry_after_seconds == 25
    assert released.allowed
    assert released.retry_after_seconds is None
    with pytest.raises(ValueError, match="timezone-aware"):
        rate_limit_gate(datetime(2026, 1, 1), now=NOW)
