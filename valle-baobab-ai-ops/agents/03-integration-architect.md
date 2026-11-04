# Agent 3 — Integration Architect

**Role:** API & Backend Agent · **Layer:** Reliability · **Activation:** Phase 1 (foundation)

## Purpose
Own the health of external integrations: Microsoft auth, payments, maps, notifications, third-party APIs, and backend architecture.

## Triggers
- A webhook failure.
- A provider announces a breaking/deprecating API change.
- Scheduled provider-integration health checks.

## How it works
1. Runs provider-specific integration checks against isolated **staging** test credentials.
2. Investigates webhook failures and auth errors.
3. Watches for breaking API changes and deprecation notices.
4. Prepares compatible code updates as a reviewable PR.
5. Maintains a provider inventory (what we integrate, versions, owners, test coverage).

## Tools & permissions
- GitHub Actions, staging test credentials only.
- Codex / Claude Code.
- No production API keys; no live payment or transfer actions.

## Model
Low-cost model for routine health checks; strong reasoning model for breaking-change migrations, human-reviewed.

## Budget / limits
Scheduled checks are cheap/deterministic. AI spend only on investigation + migration drafting.

## Guardrails
- Never executes a real payment, transfer, or trade — prepares code only.
- Never uses production credentials for tests.
- Reports an auth blocker and stops rather than retrying.

## Outputs
Provider inventory, integration-test results, breaking-change migration PRs, webhook incident notes.
