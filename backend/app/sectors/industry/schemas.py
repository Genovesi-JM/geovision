"""HTTP contracts for Industry, Energy and Utilities capabilities."""

from pydantic import BaseModel


class IndustryCapabilitiesOut(BaseModel):
    sector: str
    public_sector: str
    enabled: bool
    maturity: str
    capability_version: str
    asset_types: list[str]
    dataset_types: list[str]
    kpis: list[dict[str, str]]
    evidence_guardrails: list[str]


__all__ = ["IndustryCapabilitiesOut"]
