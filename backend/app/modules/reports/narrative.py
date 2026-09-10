"""Safe deterministic narrative implementation owned by the reports domain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class DeterministicNarrativeProvider:
    provider_name = "deterministic"
    model_name = None
    model_version = "geovision-deterministic-v1.0.0"

    def generate(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        kpis = context.get("kpis") or []
        observations = context.get("observations") or []
        actions = context.get("actions") or []
        if kpis or observations:
            summary = (
                "This report presents validated asset intelligence and its supporting evidence. "
                "Measured facts appear only in the evidence tables."
            )
        else:
            summary = (
                "The available evidence is insufficient for a measured asset assessment. "
                "The limitations section identifies the required follow up."
            )
        findings = (
            "Validated findings are listed with their source, confidence, and measurement time."
            if observations
            else "No validated findings are available for narrative interpretation."
        )
        action_text = (
            "Open follow up actions are listed for accountable review."
            if actions
            else "No evidence backed open actions are included."
        )
        evidence_ids = [
            str(item["evidence_id"])
            for group in (kpis, observations, actions)
            for item in group
            if isinstance(item, Mapping) and item.get("evidence_id")
        ]
        return {
            "schema_version": "geovision.report-narrative.v1",
            "executive_summary": summary,
            "sections": [
                {
                    "heading": "Validated findings",
                    "paragraphs": [findings],
                },
                {
                    "heading": "Recommended follow up",
                    "paragraphs": [action_text],
                },
            ],
            "evidence_ids": evidence_ids,
            "limitations": [
                "Interpretation is limited to validated evidence available in GeoVision."
            ],
        }


__all__ = ["DeterministicNarrativeProvider"]
