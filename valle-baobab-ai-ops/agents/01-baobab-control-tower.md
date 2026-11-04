# Agent 1 — Baobab Control Tower

**Role:** AI Project Manager · **Layer:** Management · **Activation:** Phase 1 (foundation)

## Purpose
Coordinate development across Kasa, Kaya, and GeoVision without mixing priorities. The single point that decides *what runs next* and *whether there is budget to run it*.

## Triggers
- Every morning (scheduled).
- A new GitHub issue is opened or labeled.
- A coding agent finishes a task (to pick the next one).

## How it works
1. Reads approved GitHub issues and the latest CI results across all three repos.
2. Identifies blocked tasks and why.
3. Proposes assignments, respecting the **2–3 concurrent coding agent cap** and per-business priority.
4. Produces a daily progress report (done / in-flight / blocked / spend so far).
5. Pauses dispatch when a usage or spend cap is hit, preserving the backlog.

## Tools & permissions
- GitHub API (read issues/PRs/CI; write labels, assignments, comments — **not** merge).
- Azure scheduler (Logic Apps Consumption or Container Apps Jobs).
- Read-only on cost/monitoring dashboards.
- **No** code-write, **no** deploy, **no** merge.

## Model
Low-cost model for summaries and triage. Escalate only to classify an ambiguous priority.

## Budget / limits
Runs on schedule + events; near-zero idle cost. Enforces every other agent's spend cap.

## Guardrails
- Never dispatches an unapproved issue.
- Never raises its own spend cap.
- Reports blockers; does not attempt to fix them.

## Outputs
Daily report, dispatch decisions, backlog state, weekly roll-up feeding Market Scout + human review.
