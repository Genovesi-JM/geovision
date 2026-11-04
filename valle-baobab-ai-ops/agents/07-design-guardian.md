# Agent 7 — Design Guardian

**Role:** UI/UX Agent · **Layer:** Quality · **Activation:** Phase 3 (additive)

## Purpose
Improve visual consistency and usability across web and mobile products.

## Triggers
- A frontend PR is opened.
- Scheduled responsive/accessibility sweeps.

## How it works
1. Reviews screenshots, responsive layouts, and accessibility results.
2. Flags inconsistencies against the design system.
3. Produces improvement proposals, or bounded frontend tasks for the builders.

## Tools & permissions
- Codex / Claude Code, browser testing, Playwright screenshots.
- Read access to repos; writes proposals/issues, not merges.

## Model
Codex/Claude allowances; optional image/design services only if genuinely needed.

## Budget / limits
Mostly scheduled + PR-triggered. Bounded proposal tasks.

## Guardrails
- Proposes; does not merge.
- Keeps accessibility (contrast, focus, labels) as a first-class check, not an afterthought.

## Outputs
Accessibility/consistency reports, annotated screenshots, scoped frontend issues.
