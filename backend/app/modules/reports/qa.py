"""Report narrative validation and deterministic review classification."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from pydantic import ValidationError

from app.modules.reports.domain import ReportError, ReportQALevel
from app.modules.reports.schemas import NarrativeEnvelope


_NUMERIC_LITERAL = re.compile(r"(?<![A-Za-z])[-+]?\d(?:[\d.,]*\d)?(?![A-Za-z])")


def _prose(envelope: NarrativeEnvelope) -> list[str]:
    values = [envelope.executive_summary, *envelope.limitations]
    for section in envelope.sections:
        values.extend((section.heading, *section.paragraphs))
    return values


def validate_narrative(
    value: Mapping[str, Any],
    *,
    evidence_ids: frozenset[str],
) -> NarrativeEnvelope:
    """Reject shape drift, unknown evidence, and every provider-authored number."""

    try:
        envelope = NarrativeEnvelope.model_validate(value, strict=True)
    except ValidationError as exc:
        raise ReportError(
            "invalid_narrative",
            "Narrative provider returned an unsupported structured response",
        ) from exc
    unknown = set(envelope.evidence_ids) - set(evidence_ids)
    if unknown:
        raise ReportError(
            "unknown_evidence",
            "Narrative provider referenced evidence outside the report context",
        )
    if any(_NUMERIC_LITERAL.search(text) for text in _prose(envelope)):
        raise ReportError(
            "invented_numeric_claim",
            "Narrative prose cannot contain numeric literals; facts are rendered from context",
        )
    return envelope


def classify_qa(
    context: Mapping[str, Any],
    *,
    narrative_provider: str,
    fallback_used: bool,
) -> tuple[ReportQALevel, dict[str, Any]]:
    observations = list(context.get("observations", []))
    kpis = list(context.get("kpis", []))
    selection = context.get("selection", {})
    exclusions = selection.get("exclusions", {}) if isinstance(selection, Mapping) else {}
    critical = sum(
        1
        for item in observations
        if isinstance(item, Mapping) and item.get("severity") == "CRITICAL"
    )
    warning = sum(
        1
        for item in observations
        if isinstance(item, Mapping) and item.get("severity") == "WARNING"
    )
    excluded = sum(
        int(value)
        for value in exclusions.values()
        if isinstance(value, int) and not isinstance(value, bool)
    )
    reasons: list[str] = []
    if critical:
        level = ReportQALevel.SPECIALIST_REVIEW
        reasons.append("validated_critical_observation")
    elif narrative_provider != "deterministic":
        level = ReportQALevel.HUMAN_REVIEW
        reasons.append("external_narrative_provider")
    elif fallback_used:
        level = ReportQALevel.HUMAN_REVIEW
        reasons.append("narrative_provider_fallback")
    elif warning or excluded or not kpis:
        level = ReportQALevel.HUMAN_REVIEW
        if warning:
            reasons.append("validated_warning_observation")
        if excluded:
            reasons.append("evidence_excluded_by_policy")
        if not kpis:
            reasons.append("no_eligible_kpis")
    else:
        level = ReportQALevel.AUTO_APPROVED
        reasons.append("deterministic_validated_low_risk_context")
    return level, {
        "schema_version": "geovision.report-qa.v1",
        "level": level.value,
        "reasons": reasons,
        "fallback_used": fallback_used,
        "eligible_kpi_count": len(kpis),
        "validated_observation_count": len(observations),
        "critical_observation_count": critical,
        "warning_observation_count": warning,
        "excluded_evidence_count": excluded,
    }


__all__ = ["classify_qa", "validate_narrative"]
