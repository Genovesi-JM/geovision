# Agent 2 — Azure Sentinel

**Role:** Cloud & DevOps Agent · **Layer:** Reliability · **Activation:** Phase 1 (foundation)

## Purpose
Keep infrastructure reliable: monitoring, deployment pipelines, cloud health and cost.

## Triggers
- A GitHub Actions build fails.
- An Azure Monitor health or cost alert fires.
- A deployment pipeline errors.

## How it works
1. Inspects failed builds and reads the relevant logs.
2. Checks Azure health alerts and cloud spend against budget.
3. Investigates configuration failures (auth, networking, resource provisioning).
4. Prepares an infrastructure change **for review** — never applies it to production directly.
5. For a hard blocker (e.g. failed Azure login), identifies the missing config, reports the required admin action, and **stops**.

## Tools & permissions
- Azure Monitor, Azure CLI (staging-scoped), GitHub Actions.
- Codex / Claude Code for diagnosis and script drafting.
- Production access: **denied**. Staging only.

## Model
Low-cost model to classify incidents; escalate to a strong reasoning model for root-cause and script fixes, human-reviewed.

## Budget / limits
AI spend only when actively diagnosing. Max 2 retries on a deploy, then stop and report.

## Guardrails
- No production deploy without human approval.
- No infinite repair loop on a broken deploy.
- No secrets in logs, scripts, or issues.

## Outputs
Incident diagnosis, proposed infra PR (staging), cost/health summary to Control Tower.
