# Cursor Skills Lifecycle Map

Canonical agent workflows live in `.cursor/skills/<name>/SKILL.md` only. No `.cursor/commands/` layer.

## Canonical Ownership Matrix

| Workflow Area | Canonical Skill | Secondary Skill(s) | Notes |
|---|---|---|---|
| Session bootstrap | `bootstrap` | `build-phase`, `research` | Lifecycle routing from `docs/CONTEXT.md`. |
| PM2 restart (local ops) | `restart` | `bootstrap` | Backend/frontend/tunnel/prod-ui via `scripts/ops_pm2.sh`. |
| Commit/push + hook repair | `commit` | `general-rules` | `commit` owns landing workflow; `general-rules` owns cross-cutting defaults. |
| Cross-cutting defaults | `general-rules` | none | uv, ruff, diagnose/TDD, scripting, doc discipline. |
| Replay/resume drill | `resume` | `lit-review` | Engineering replay after `src/` changes; `lit-review` for operator/WhatsApp flows. |
| Skill authoring | `author` | `inception`, `general-rules` | `author` owns structure; `inception` extracts learnings. |
| Session learning extraction | `inception` | `author`, `handoff` | Retrospective extraction into skills/gotchas. |
| External research | `research` | `grill` | MCP-backed discovery vs local plan pressure-testing. |
| Plan pressure-testing | `grill` | `research` | One question at a time against repo contracts. |
| Hard-decision escalation | `advisor` | `grill`, `research` | Readonly PLAN/CORRECTION/STOP; not a substitute for grilling. |
| Minimal-diff / YAGNI | `ponytail` | none | Does not override project invariants. |
| Architecture review | `architecture` | `grill` | Structural boundary/debt review before large refactors. |
| Session transfer | `handoff` | `bootstrap` | Compact next-agent package. |
| Runtime review ops | `lit-review` | `db-audit`, `bootstrap` | Operator playbook (symlink to `skills/lit-review`). |
| Dashboard UI taste | `frontend` | none | Project dashboard tokens; marketing pages use global `design-taste-frontend`. |
| Response compression | `caveman` | none | Style mode only. |

## Default Skills (Use First)

- `bootstrap` - session startup and routing
- `restart` - PM2 backend/frontend/tunnel restart (`/restart`)
- `build-phase` - phase router and implementation contract
- `general-rules` - cross-cutting engineering defaults
- `research` - MCP-backed research (Ref/Exa/Perplexity)
- `db-audit` - evidence-first runtime DB verification

## Domain Skills

- `dual-reviewer`, `quality`, `meta-analysis`, `section-writer`, `prisma`, `ieee`, `humanizer`

## Specialist / Optional

- `lit-review` (operator playbook at `skills/lit-review`, linked into `.cursor/skills/lit-review`)
- `protocol`, `connectors`, `prototype`, `citations`, `frontend`

## Collaboration / Meta

- `grill`, `handoff`, `author`, `inception`, `advisor`, `ponytail`, `architecture`, `caveman`, `commit`, `restart`, `resume`

## Overlap Boundaries

- `research` vs `grill`: external sources vs local contract pressure-testing.
- `advisor` vs `grill`: escalation vs user interview; not interchangeable.
- `ponytail` vs `caveman`: build laziness vs response compression.
- `frontend` vs global `design-taste-frontend`: dashboard vs marketing/landing.
- `commit` vs `general-rules`: ship workflow vs cross-cutting defaults.
- `resume` vs `lit-review`: engineering replay drill vs operator E2E playbook.

## Skill Authoring Contract

1. Trigger and scope
2. Required inputs
3. Expected outputs
4. Stop and escalation rules
5. Verification checklist

## Build-Phase Contract

Use `build-phase` when implementing or validating build phases. Distinguish build phase labels (1-8) from backend runtime checkpoint keys. Read `docs/ARCHITECTURE.md#pipeline`, `docs/ARCHITECTURE.md`, and `docs/TASKS.md` before phase edits.
