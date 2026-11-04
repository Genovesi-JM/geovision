# Labels

Apply to every repo. Create them with the script at the bottom.

| Label | Color | Meaning |
|---|---|---|
| `workstream:kasa` | `#1f6feb` | Kasa work |
| `workstream:kaya` | `#2da44e` | Kaya Saúde work |
| `workstream:geovision` | `#bf8700` | GeoVision work |
| `workstream:platform` | `#6e7781` | Shared infra / agent config |
| `priority:p0` | `#b60205` | Users blocked / outage |
| `priority:p1` | `#d93f0b` | Important, soon |
| `priority:p2` | `#fbca04` | Normal |
| `priority:p3` | `#0e8a16` | Low / cosmetic |
| `agent-eligible` | `#5319e7` | May be dispatched to an AI agent |
| `needs-scoping` | `#c5def5` | Not yet a single scoped task |
| `blocked` | `#000000` | Waiting on an external action |
| `security` | `#b60205` | Security-sensitive; Quality Gatekeeper must review |
| `needs-human-approval` | `#d4c5f9` | Requires explicit human sign-off (prod, payments, sends) |

## Create them

```bash
REPO="valle-baobab/geovision"   # repeat per repo

gh label create "workstream:kasa"        -c "1f6feb" -d "Kasa work"                 --repo "$REPO" --force
gh label create "workstream:kaya"        -c "2da44e" -d "Kaya Saude work"           --repo "$REPO" --force
gh label create "workstream:geovision"   -c "bf8700" -d "GeoVision work"            --repo "$REPO" --force
gh label create "workstream:platform"    -c "6e7781" -d "Shared infra / agent cfg" --repo "$REPO" --force
gh label create "priority:p0"            -c "b60205" -d "Users blocked / outage"    --repo "$REPO" --force
gh label create "priority:p1"            -c "d93f0b" -d "Important, soon"           --repo "$REPO" --force
gh label create "priority:p2"            -c "fbca04" -d "Normal"                    --repo "$REPO" --force
gh label create "priority:p3"            -c "0e8a16" -d "Low / cosmetic"            --repo "$REPO" --force
gh label create "agent-eligible"         -c "5319e7" -d "Dispatchable to an agent"  --repo "$REPO" --force
gh label create "needs-scoping"          -c "c5def5" -d "Not yet a scoped task"     --repo "$REPO" --force
gh label create "blocked"                -c "000000" -d "Waiting on external action"--repo "$REPO" --force
gh label create "security"               -c "b60205" -d "Security-sensitive"        --repo "$REPO" --force
gh label create "needs-human-approval"   -c "d4c5f9" -d "Requires human sign-off"   --repo "$REPO" --force
```
