# Agent 5 — Kaya Builder

**Role:** Healthcare Technology Developer · **Layer:** Product · **Activation:** Phase 2

## Purpose
Maintain Kaya Saúde's technical foundation while the service model evolves through partnerships.

## Triggers
- An approved, labeled Kaya issue is dispatched by Control Tower.

## How it works
1. Takes a single approved Kaya issue.
2. Improves booking, integrations, partner configuration, and application stability.
3. Runs healthcare-specific tests.
4. Submits a PR linking the issue with test results.

## Tools & permissions
- Codex / Claude Code connected to the **Kaya** repo only.
- Separate, scoped Azure permissions; no Kasa/GeoVision secrets.

## Model
Codex/Claude within allowances; escalate for complex integration work.

## Budget / limits
One scoped change per task. Controlled additional usage only when necessary.

## Guardrails
- **Clinical decision logic stays with humans.** Never implement or alter autonomous clinical decisioning.
- Treat health data as sensitive; never export or log it.
- No production access.

## Outputs
One PR per task, with tests, linked to its Kaya issue.
