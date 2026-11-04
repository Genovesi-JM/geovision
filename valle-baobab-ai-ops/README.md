# Valle Baobab AI Operations — starter kit

Version-controlled definitions, runbooks, and templates for running AI agents across **Kasa**, **Kaya Saúde**, and **GeoVision**. Azure-first, GitHub-controlled, 9 agent roles, at most 2–3 coding agents at once.

> ⚠️ These files **describe and configure** the system. Creating them does not *start* any agent — your chosen platform (Codex / Claude Code / an orchestrator) must load `AGENTS.md` + `agents/`, and you must run the Azure/GitHub setup against your real accounts.

## What's here

```
valle-baobab-ai-ops/
├── README.md                    ← you are here
├── AGENTS.md                    ← shared operating contract (read first)
├── CLAUDE.md                    ← Claude Code–specific instructions
├── agents/                      ← the 9 agent role definitions
│   ├── 01-baobab-control-tower.md
│   ├── 02-azure-sentinel.md
│   ├── 03-integration-architect.md
│   ├── 04-kasa-builder.md
│   ├── 05-kaya-builder.md
│   ├── 06-geovision-builder.md
│   ├── 07-design-guardian.md
│   ├── 08-quality-gatekeeper.md
│   └── 09-market-scout.md
├── docs/
│   ├── installation-plan.md     ← the full plan (polished)
│   ├── azure-oidc-setup.md      ← Step 1 runbook: GeoVision staging auth fix
│   └── github-backlog.md        ← board structure + process
├── scripts/
│   └── azure-oidc-setup.sh      ← runnable OIDC setup (edit vars, then run)
└── .github/
    ├── labels.md                ← label set + creation script
    └── ISSUE_TEMPLATE/
        ├── agent-task.md        ← the only agent-dispatchable template
        ├── bug.md
        └── incident.md
```

## Do this in order

1. **Read** [`AGENTS.md`](AGENTS.md) — the golden rules bind every agent.
2. **Fix the blocker first.** Follow [`docs/azure-oidc-setup.md`](docs/azure-oidc-setup.md); edit the vars in [`scripts/azure-oidc-setup.sh`](scripts/azure-oidc-setup.sh) and run it. **Test login before creating more resources.**
3. **Stand up the board.** Follow [`docs/github-backlog.md`](docs/github-backlog.md); apply labels from [`.github/labels.md`](.github/labels.md); copy `.github/ISSUE_TEMPLATE/` into each repo.
4. **Load the agent roles** into Codex / Claude Code (connect `AGENTS.md` + `agents/` + `CLAUDE.md`).
5. **Activate the foundation agents** (1 Control Tower, 2 Azure Sentinel, 3 Integration Architect, 8 Quality Gatekeeper), then the builders, then Design Guardian + Market Scout.
6. **Prove one full cycle:** approved issue → agent PR → tests pass → human approves → cost + outcome recorded.

## Where to put this

Suggested: a private `valle-baobab/platform` repo that holds `AGENTS.md`, `agents/`, and shared workflows. Each business repo (`kasa`, `kaya`, `geovision`) gets the `.github/` templates + labels and its own `CLAUDE.md` if needed.

## Non-negotiables (full list in AGENTS.md)
- Staging first; humans merge; no self-approval.
- One scoped change per task; every task has a budget and an exit.
- Secrets in Key Vault / OIDC — never in these files.
- Kasa / Kaya / GeoVision contexts stay isolated.
- Clinical, financial, and legal decisions stay with humans.
- A hard blocker is **reported and stopped**, never looped.

---
*Generated as a planning/configuration starter kit, November 2026. Prices and model names are point-in-time and should be re-checked before you commit spend.*
