# GitHub Backlog & Project Board

The control plane for all agent work. One GitHub Project, three workstreams, strict entry criteria so agents only ever pick up well-formed tasks.

---

## Board structure

Create a **GitHub Project (v2)** named `Valle Baobab Operations`. Use a single board with a **Workstream** field so Kasa, Kaya, and GeoVision stay separate but visible together.

**Fields:**
| Field | Type | Values |
|---|---|---|
| Workstream | Single select | `Kasa`, `Kaya`, `GeoVision`, `Platform` |
| Status | Single select | `Backlog`, `Ready`, `In progress`, `In review`, `Blocked`, `Done` |
| Priority | Single select | `P0`, `P1`, `P2`, `P3` |
| Agent | Single select | the 9 agent names + `Human` |
| Automation eligible | Single select | `Yes`, `No`, `Needs scoping` |
| Spend cap | Text | e.g. `$5` |

**`Ready` = dispatchable.** The Control Tower only assigns issues in `Ready` that are `Automation eligible = Yes`. An issue reaches `Ready` only when it has: clear owner, acceptance criteria, priority, expected output, approval rule.

**Views:**
- *By workstream* (board grouped by Workstream)
- *Dispatch queue* (filter: Status=Ready, Automation eligible=Yes, sorted by Priority)
- *Blocked* (Status=Blocked — the Control Tower's daily report reads this)
- *In review* (open PRs awaiting human approval)

---

## Create it with the CLI

```bash
# Create the project (owner = your org or user)
gh project create --owner valle-baobab --title "Valle Baobab Operations"

# Repos (one per business + a platform repo for infra/agent config)
# gh repo create valle-baobab/kasa       --private
# gh repo create valle-baobab/kaya       --private
# gh repo create valle-baobab/geovision  --private
# gh repo create valle-baobab/platform   --private   # holds AGENTS.md, agents/, workflows
```

Fields on Projects v2 are added in the UI or via `gh project field-create`. Keep this file as the source of truth for what the fields should be.

---

## Labels

Apply these to every repo. See [`.github/labels.md`](../.github/labels.md) for the full list and a script to create them.

Core set: `workstream:kasa`, `workstream:kaya`, `workstream:geovision`, `workstream:platform`, `priority:p0..p3`, `agent-eligible`, `needs-scoping`, `blocked`, `security`, `needs-human-approval`.

---

## Issue templates

In [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/):
- `agent-task.md` — the only template that produces agent-dispatchable work. Forces acceptance criteria, scope, and approval rule.
- `bug.md` — a defect report (may become an agent task after scoping).
- `incident.md` — an infra/integration incident for Azure Sentinel / Integration Architect.

---

## Entry criteria checklist (the "Ready" gate)

An issue is **not** dispatchable to an agent until all are true:
- [ ] Single, scoped change (one PR's worth).
- [ ] Acceptance criteria written and testable.
- [ ] Workstream + Priority + Agent set.
- [ ] Expected output stated (what the PR should contain).
- [ ] Approval rule stated (who reviews, what must be green).
- [ ] Spend cap set.
- [ ] No production access required (or flagged `needs-human-approval` if it does).

---

## Weekly / daily cadence (driven by Control Tower)

- **Daily:** Control Tower posts a report — Ready count, In progress, Blocked (with reasons), spend so far.
- **New issue:** auto-categorized; set to `needs-scoping` unless it already meets the Ready gate.
- **Usage/spend cap hit:** dispatch pauses; backlog preserved; report says so.
