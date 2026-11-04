# CLAUDE.md — Claude Code instructions for Valle Baobab

This file is loaded automatically by Claude Code. It applies on top of [`AGENTS.md`](AGENTS.md), which holds the shared operating contract for **all** agents. Read AGENTS.md first.

Claude Code's role in this system: **engineering and complex debugging** — architecture, integration work, difficult code problems, and Azure-related scripts. For routine, well-scoped changes, Codex is the cheaper default; escalate to Claude Code when a task needs stronger reasoning.

## How Claude Code should work here

- **One scoped change per branch.** Branch name: `agent/<business>/<issue-number>-<slug>` (e.g. `agent/geovision/142-fix-adapter-retry`).
- **Staging only.** Never run commands against production credentials or production Azure resources.
- **Run tests before opening a PR.** Include the test output in the PR body. If tests can't run, say so explicitly in the PR — never imply they passed.
- **Isolated workspaces.** Use a git worktree or cloud workspace per task so concurrent work never collides.
- **Stop at blockers.** If something is blocked on an admin action (missing Azure role, unconfigured OIDC, absent secret), report exactly which action is needed and stop. Do not generate new infrastructure or retry a broken deploy in a loop.
- **Secrets.** Read credentials only from the environment / Key Vault references the task provides. Never print a secret, never commit one, never add one to this repo.

## Per-business notes

- **Kasa** — verify tenant isolation and auth rules on any change that touches listings, messaging, or landlord workflows.
- **Kaya Saúde** — keep clinical decision logic out of autonomous changes. Touch booking, integrations, partner config, and stability only.
- **GeoVision** — when creating demos or validating pipelines with synthetic data, label it synthetic. Never present generated data as real field evidence.

## Commit / PR conventions

- Conventional-commit style subject: `fix(geovision): retry provider adapter on 503`.
- PR must link its issue (`Closes #<n>`), list what changed, and show test results.
- Humans review and merge. Claude Code does not self-merge or enable auto-merge unless a human explicitly asks.

## First technical objective

The current priority is the **GeoVision Azure authentication blocker** (staging login failed before deployment), then a verified staging deploy. See [`docs/azure-oidc-setup.md`](docs/azure-oidc-setup.md).
