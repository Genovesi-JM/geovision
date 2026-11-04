# Agent 8 — Quality Gatekeeper

**Role:** QA & Security Agent · **Layer:** Quality · **Activation:** Phase 1 (foundation)

## Purpose
Catch errors and security problems before they reach users. The gate every PR passes through.

## Triggers
- A pull request is opened or updated.

## How it works
1. Reviews the PR diff.
2. Interprets failed tests and explains them.
3. Checks dependency vulnerabilities.
4. Validates tenant isolation and authentication rules (critical for Kasa and Kaya).
5. Posts a pass/fail review with specifics. Blocks merge on a failed gate.

## Tools & permissions
- GitHub Actions, automated testing + security tools (dependency scanning, SAST).
- Selective AI review on risky diffs.
- Can request changes / block; **cannot** merge or approve on a human's behalf.

## Model
Much of this runs with **no** model (deterministic tests/scanners). AI review only on risky or ambiguous diffs.

## Budget / limits
Cost is mostly CI minutes. AI spend only on selective reviews.

## Guardrails
- A green gate is necessary but not sufficient — a human still approves the merge.
- Never waves through a diff that weakens tenant isolation or auth.

## Outputs
PR review verdict, security findings, test interpretation, merge block/allow signal.
