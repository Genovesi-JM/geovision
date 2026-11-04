# Valle Baobab Group — AI Agent Installation Plan

**November 2026 · Azure-first · Kasa, Kaya Saúde and GeoVision**

> **Recommendation in one line:** 9 specialized agent *roles*, operating through 4 core systems, with at most 2–3 coding agents running at once — built on the subscriptions you already have, adding paid platforms only when a real problem demands them.

You do **not** need nine AI subscriptions, nine powerful computers, or nine always-on servers. Most roles share models and wake only when a task, schedule, or system event needs them. Your existing **ChatGPT Plus** and **Claude Pro** stay the primary development tools; their coding capability is already inside the plan limits. Extra API usage for fully unattended agents is billed separately.

---

## 1. The four core systems

| System | Role in the stack | What it does |
|---|---|---|
| **Microsoft Azure** | Automation infrastructure | Scheduled jobs, service monitoring, cloud identity, secret protection (Key Vault), cost tracking. Valle Baobab's main cloud platform. |
| **GitHub** | Development control center | The three repos, agent assignments, CI tests, branches, PRs, approval history, the Projects board. |
| **OpenAI Codex** | Cloud coding & review | Works approved tasks, creates changes, reviews code without step-by-step supervision. |
| **Claude Code** | Engineering & complex debugging | Architecture, integrations, hard code problems, Azure scripts — on your Claude Pro allowance. |

The nine agents are **configurations** (instructions, restricted tools, an approved queue, a budget) built on top of these four products — not nine separate pieces of software to buy.

---

## 2. The nine agents

Each has instructions, restricted tools, an approved task queue, and an execution budget. Full definitions: [`../agents/`](../agents/) and the shared contract in [`../AGENTS.md`](../AGENTS.md).

| # | Agent | Purpose | Activate |
|---|---|---|---|
| 1 | **Baobab Control Tower** (PM) | Coordinate work across all three businesses without mixing priorities. | Phase 1 |
| 2 | **Azure Sentinel** (Cloud/DevOps) | Infra reliability, monitoring, pipelines, cost. | Phase 1 |
| 3 | **Integration Architect** (API/Backend) | Microsoft auth, payments, maps, notifications, third-party APIs. | Phase 1 |
| 4 | **Kasa Builder** | Marketplace, listings, messaging, landlord workflows. | Phase 2 |
| 5 | **Kaya Builder** | Booking, integrations, partner config, stability (clinical logic stays human). | Phase 2 |
| 6 | **GeoVision Builder** | Field-data ingestion, dashboards, reports, device integrations. | Phase 2 |
| 7 | **Design Guardian** (UI/UX) | Visual consistency, responsive layout, accessibility. | Phase 3 |
| 8 | **Quality Gatekeeper** (QA/Security) | Reviews PRs, tests, dependency vulns, tenant isolation & auth. | Phase 1 |
| 9 | **Market Scout** (Business) | Competitor research, partnership briefs, pricing, pilot lists (prepares, never sends). | Phase 3 |

**Activate 1, 2, 3, 8 first** — the management + reliability foundation. Product builders work against that stable base; Design Guardian and Market Scout are additive.

---

## 3. How everything connects

```
Schedule  ·  GitHub event  ·  Azure alert
                │
                ▼
      Baobab Control Tower
   approved backlog · priority · spend caps
                │
      ┌─────────┴─────────┐
      ▼                   ▼
 Coding agents       Operations agents
 Codex / Claude      Azure Jobs / model APIs
      │                   │
      └─────────┬─────────┘
                ▼
 GitHub Issues → Branches → Pull Requests
                │
                ▼
 Automated checks + human approval
                │
                ▼
 Staging first → controlled production
```

### Installation sequence
1. **Configure Azure authentication.** Scoped Entra identity + GitHub OIDC federation + correct IDs + staging permissions. **Test login before creating any further resources.** → [`azure-oidc-setup.md`](azure-oidc-setup.md)
2. **Create the GitHub project board.** Separate Kasa / Kaya / GeoVision workstreams; every task has owner, acceptance criteria, priority, expected output, approval rule. → [`github-backlog.md`](github-backlog.md)
3. **Configure the agent roles.** Version-controlled `AGENTS.md`, `CLAUDE.md`, `agents/`. *Creating the files does not start the agents* — the chosen platform must load these definitions.
4. **Connect Codex & Claude Code.** Sign in to Codex (ChatGPT / CLI / IDE); install Claude Code and authenticate on Claude Pro. Connect each to the right repo, ideally isolated worktrees or cloud workspaces.
5. **Add automatic triggers.** GitHub Actions for CI/PR checks/dependency alerts; Azure Logic Apps Consumption or Container Apps Jobs for scheduled/event-driven work.
6. **Add cost, security & release controls.** Limited credentials, no production access by default, capped tasks/retries, cost monitoring, review before merge/deploy. Secrets in Key Vault — never in instruction files.

> Technical note: ChatGPT Plus / Claude Pro power interactive sessions, but a custom Azure job **cannot** use those subscriptions as unlimited API credits. Fully unattended custom model calls generally need separately metered API access.

---

## 4. Costs

Public list prices, checked November 2026. Taxes, regional rates, and optional usage can change totals.

| Provider / Product | Published price | Decision |
|---|---|---|
| ChatGPT Plus + Codex | already subscribed; Plus ~$20/mo | **Keep** |
| Claude Pro + Claude Code | already subscribed; ~$20/mo | **Keep** |
| GitHub Actions | Free tier incl. 2,000 private-repo min/mo | **Use now** |
| Azure Container Apps Jobs | consumption-based; free grants may apply | **Use for scheduled work** |
| Azure Logic Apps Consumption | metered; first 4,000 built-in actions free | Good Azure-native option |
| GitHub Copilot Pro | $10/mo/user | Optional |
| n8n Starter Cloud | €20/mo billed annually | Optional (visual automation) |
| LangSmith Developer | $0/seat, 5,000 base traces/mo | Optional (observability) |
| CrewAI Basic | free, 50 runs/mo | Evaluation only |
| Microsoft Foundry Agent Service | usage-billed | Consider later |

**Selected stack:** Azure + GitHub + Codex + Claude Code, plus *one* optional orchestration framework later.

### November budget scenarios (spending *limits*, not guaranteed cost or output)
| Tier | Extra-AI spend cap |
|---|---|
| Lean | $0–25 |
| **Balanced (chosen)** | **$25–75** |
| Intensive | $100–250 |

Choose **Balanced**, but fund only a small amount of metered API use at first; raise it after you can measure successful tasks per dollar. **Azure infrastructure is budgeted separately** — databases, networking, and logs cost money even with zero AI activity. An Azure-only setup is not automatically a cheap one.

### Model routing
| Task | Approach |
|---|---|
| Issue categorization, summaries | Low-cost model |
| API incident classification | Low-cost model; escalate when uncertain |
| Routine code changes | Codex/Claude within allowances |
| Complex architecture & security | Strong reasoning model, human-reviewed |
| Recurring deterministic tests | No model at all |

> Example low-cost model: a GPT-5.4 Mini-class model (~$0.75 / 1M input, ~$4.50 / 1M output tokens) suits simple automated tasks — not necessarily best for repository-wide development.

---

## 5. Other companies to evaluate (in order, not all at once)

- **Microsoft Foundry** — best Azure-native candidate for permanent multi-agent hosting (model selection, tools, tracing, identity).
- **n8n** — visual automation (API/DB/webhook/AI nodes); self-hostable on Azure, but you maintain it.
- **LangGraph / LangSmith** — precise control over multi-agent workflows, persistence, routing, observability. More technical.
- **CrewAI** — role-based multi-agent teams; worth testing for the nine-agent structure, not an immediate production dependency.
- **GitHub Copilot** — interesting for assigning issues directly to cloud coding agents and getting async PRs; from $10/mo.

Do **not** buy extra Copilot, Cursor, CrewAI enterprise, or a paid n8n plan right now. First learn what your existing subscriptions + GitHub can do.

---

## 6. The daily workflow

| Trigger | Automated response |
|---|---|
| Every morning | Control Tower checks approved tasks, reports blockers |
| New GitHub issue | Categorize; decide if it meets automation criteria |
| Approved dev task | Dispatch to an available coding agent |
| New pull request | Run unit tests, security checks, relevant UI tests |
| Failed CI build | Azure Sentinel / QA investigates, prepares a diagnosis |
| API/hosting alert | Investigate; escalate or propose a safe fix |
| Weekly | Send business, technical, and cost reports |
| Usage limit reached | Pause new AI tasks, preserve the backlog |

A failed test must **never** become an unlimited repair loop. Every task has a max runtime, retry count, spend allowance, and exit condition. Example: if the GeoVision Azure login fails again, the system identifies the missing config, reports the required admin action, and **stops** — it does not keep generating new infrastructure or retrying the broken deploy.

---

## 7. November priorities

> Planning checklist — this document and the files beside it do not *start* any agent.

1. Verify Azure OIDC connection — resolve GeoVision staging authentication.
2. Establish GitHub backlog — separate the three workstreams.
3. Configure Control Tower — scheduling, priorities, reports.
4. Configure Azure Sentinel — cloud health, errors, cost.
5. Configure Integration Architect — provider inventory + integration tests.
6. Connect the three development agents — Kasa, Kaya, GeoVision.
7. Activate quality controls — CI tests, security, review gates.
8. Add design and business agents — usability + commercial research.
9. Test one automated task cycle — one approved issue through a verified PR.

**The key evidence of success** is one complete automated task lifecycle: an approved issue is assigned, an agent produces code, tests pass, a human approves, and the system records cost and outcome. After that, the workflow repeats across all three repos without inventing a new process each time.

---

## Final recommendation

Build Valle Baobab AI Operations around the nine named roles, using the **fewest paid platforms possible**: Azure + GitHub for infrastructure and control, Codex + Claude Code for development, and a low-cost API model only for unattended work that truly needs one. Introduce Microsoft Foundry or n8n later *only* if they solve a demonstrated orchestration problem.

The first technical objective remains the **GeoVision Azure authentication blocker**, then a verified staging deploy — giving the agent system a working environment rather than more automation wrapped around a failed deployment.

The goal is not to keep nine agents busy all day. It is to keep a queue of valuable work so the next task can progress whenever capacity and budget allow — without you managing every step.
