# From these files to one working agent

A concrete, ordered path from "I have the plan" to "one agent produced a reviewed, tested PR." Do it once, end to end, for **one** repo (GeoVision is the natural choice — it has the blocker). Then repeat the pattern.

Legend: **[You]** = only you can do it (your logins/admin rights). **[You+AI]** = an agent or assistant can draft/run it, but you approve. Costs are flagged **💲**.

---

## Stage 0 — What you have (cost: $0)
20 config/doc files + one web page. Nothing is installed, logged in, or running. No agent exists. This stage costs nothing because it's just text on disk.

---

## Stage 1 — Logins & tools (cost: your existing subscriptions only)

1. **[You] Codex** — sign in through ChatGPT (you already pay ChatGPT Plus, ~$20/mo). Codex coding is inside that plan for *interactive* use.
2. **[You] Claude Code** — install on your computer, authenticate with Claude Pro (~$20/mo, already paid).
3. **[You] GitHub** — you have an account. Confirm you can create private repos under an owner (personal or a `valle-baobab` org).
4. **[You] Azure** — confirm you can sign in (`az login`) and that you have rights to create an app registration and assign a role on a resource group.

💲 **New charges here: none** beyond the two subscriptions you already pay. This stage is logins, not usage.

> Why you and not me: these are *your* accounts and credentials. I can't log into them, and the plan forbids me handling your passwords. You do the sign-ins; after that an agent can work inside them.

---

## Stage 2 — Clear the GeoVision blocker (cost: ~$0)

5. **[You] Put the files in a repo.** Create `valle-baobab/geovision` (and later `kasa`, `kaya`, `platform`). Add the GeoVision code; copy `.github/ISSUE_TEMPLATE/` into it.
6. **[You] Fix Azure login.** Follow [`azure-oidc-setup.md`](azure-oidc-setup.md): edit the variables in [`../scripts/azure-oidc-setup.sh`](../scripts/azure-oidc-setup.sh), run it, then run the `azure-login-test` workflow. **Stop when `az account show` goes green.**

💲 **New charges here: ~nothing.** OIDC setup, an app registration, and a role assignment are free. GitHub Actions minutes are free up to 2,000/mo on private repos. The login test is seconds of compute.

> This is the real step 0 of the whole system. Until login works, no agent can deploy anything.

---

## Stage 3 — Make the board & labels (cost: $0)

7. **[You+AI] Create the Project board** per [`github-backlog.md`](github-backlog.md) and apply labels from [`../.github/labels.md`](../.github/labels.md) (the `gh label create` script).
8. **[You] Write ONE real issue** using the `agent-task` template. Small and safe — e.g. "fix retry on the GeoVision provider adapter." Fill every field (acceptance criteria, scope, spend cap). Move it to **Ready**.

💲 **New charges: none.** GitHub Projects and issues are free.

---

## Stage 4 — Run ONE agent, by hand, interactively (cost: inside subscriptions)

This is the honest shortcut: don't automate yet. Prove the loop with a human (you) pressing go.

9. **[You+AI] Point Claude Code (or Codex) at the GeoVision repo**, give it the one Ready issue + `AGENTS.md` + `CLAUDE.md`, and let it work: one branch, one scoped change, run tests, open a PR.
10. **[You] Review the PR.** Check tests ran and passed (they're in the PR body). Approve and merge. Deploy to staging.
11. **[You] Record cost + outcome.** Note what it cost and whether it worked.

💲 **New charges: still inside your ChatGPT Plus / Claude Pro allowances**, because this is *interactive* use — you're driving. This is "pay only what you already pay." You've now completed one full lifecycle: the plan's definition of success.

---

## Stage 5 — Automate the trigger (this is where "pay when needed" and new bills begin)

Only now does the system run *without you pressing go* — and only now do new meters start.

12. **[You+AI] Add a trigger.** Either a GitHub Action (on new PR / on schedule) or an Azure scheduled job (Logic Apps Consumption or Container Apps Jobs) that wakes an agent on an event.
13. **[You] Decide the unattended model path.** An unattended job calling a model generally needs a **separately metered API key** — your ChatGPT Plus / Claude Pro plans are not unlimited API credits for background jobs. Start with a low-cost model and a small cap.
14. **[You] Set caps.** Per-task spend cap, max retries, max runtime, exit condition — per `AGENTS.md`.

💲 **New charges appear here, in two places:**
- **Metered model/API usage** — only when a task actually runs. This *is* the "pay when needed" part. Budget: Balanced tier, fund a small amount first.
- **Azure infrastructure** — **not** pay-when-needed. Any databases, networking, logging, or always-on resources in your GeoVision setup bill continuously, even on days no agent runs. Check this in Azure Cost Management before you leave anything provisioned.

---

## So, directly answering "are they installed / do I just pay when needed?"

| Question | Answer |
|---|---|
| Are agents installed? | No. You're at Stage 0. |
| Are they logged in? | No. Logins are Stage 1, done by you. |
| Do I pay only when needed? | **Partly.** *Model/API* usage is pay-per-use (Stage 5). *Azure infrastructure* has a standing cost regardless of agent activity. |
| When do the first new bills appear? | Not until Stage 5 (automation) for model usage — and continuously for any Azure resources you provision, from the moment they exist. |
| What should I do first? | Stages 1–4 for one repo. They cost nothing beyond your current subscriptions and prove the whole loop before you spend on automation. |

---

## The smallest useful next action
Do **Stage 1 (logins)** and **Stage 2 (Azure login fix)**. Together they cost roughly nothing, and they turn "a plan" into "a system that can actually run." Everything else waits behind a working Azure login.
