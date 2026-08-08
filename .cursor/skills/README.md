# Cursor Skills Lifecycle Map

This file maps existing skills to lifecycle stages without changing runtime behavior.
Canonical lifecycle and contract docs are under `.cursor/docs/`.

## Canonical Ownership Matrix

Use one canonical skill per workflow area. Adjacent skills should point back to the owner instead of duplicating full procedures.

| Workflow Area | Canonical Skill | Secondary Skill(s) | Notes |
|---|---|---|---|
| Session bootstrap + orientation | `general-rules` | `build-phase`, `research` | `general-rules` owns reusable startup/process defaults; lifecycle routing still comes from `.cursor/docs/INDEX.md`. |
| Commit/push + hook repair | `general-rules` | none | `general-rules` owns the full landing workflow (probe, doc sync, gate, hooks, commits, push). Use `/commit` as the thin command entrypoint. Not a standalone `commit-and-push` skill. |
| Skill authoring and de-duplication | `write-a-skill` | `general-rules`, `inception` | `write-a-skill` owns skill structure/workflow; `inception` extracts learnings into skills/gotchas; `general-rules` only provides global constraints. |
| Session learning extraction | `inception` | `write-a-skill`, `handoff` | `inception` owns retrospective extraction; `write-a-skill` for authoring structure; `handoff` for one-off session transfer without durable artifacts. |
| External research grounding | `research` | `grill-with-docs` | `research` owns source-backed discovery; `grill-with-docs` owns plan pressure-testing. |
| Plan pressure-testing | `grill-with-docs` | `research` | Use code/docs contradiction checks and decision-tree questioning here. |
| Hard-decision escalation | `advisor` | `grill-with-docs`, `research` | `advisor` owns readonly PLAN/CORRECTION/STOP escalation when the executor is stuck; not a substitute for grilling the user or external research. |
| Minimal-diff / YAGNI mode | `ponytail` | none | Style/efficiency mode only; does not override project invariants, hard exclusions, or contract ownership. |
| Architecture deepening review | `improve-codebase-architecture` | `grill-with-docs` | Structural boundary and debt review; use `grill-with-docs` when the plan itself still needs pressure-testing. |
| Session transfer/handoff | `handoff` | `general-rules` | Handoff format and next-step packaging live only in `handoff`. |
| Runtime review operations | `lit-review` | `run-database-audit`, `general-rules` | `lit-review` owns operator workflow for running/resuming/monitoring reviews with low token burn. |
| Response compression mode | `caveman` | none | Style mode only; never owns process workflows. |

## Default Skills (Use First)

- `build-phase` - phase router and implementation contract
- `general-rules` - cross-cutting engineering and safety defaults
- `research` - MCP-backed research workflow (Ref/Exa/Perplexity)
- `run-database-audit` - evidence-first runtime DB verification

## Domain Skills (Open On Demand)

- `dual-reviewer`
- `quality-assessment`
- `meta-analysis`
- `section-writer`
- `prisma-diagram`
- `ieee-export`
- `humanizer`

## Specialist / Optional Skills

- `lit-review` (runtime operator playbook; lives at `skills/lit-review` and is linked into `.cursor/skills/lit-review`)
- `protocol-generator`
- `search-connector`
- `prototype`
- `citation-ledger` (lineage reference; primary writing flow lives in `section-writer`)
- `frontend-design-taste` (dashboard UI token/taste discipline; preserve-brand, not marketing pages)

## Collaboration / Meta Skills

- `grill-with-docs` (one-question-at-a-time plan pressure testing against repo contracts)
- `handoff` (compact transfer package for next-agent continuation)
- `write-a-skill` (skill authoring, tailoring, and de-duplication workflow)
- `inception` (extract session learnings into project skills or gotchas; `/inception` retrospective)
- `advisor` (readonly hard-decision escalation: PLAN / CORRECTION / STOP)
- `ponytail` (YAGNI / minimal-diff intensity mode)
- `improve-codebase-architecture` (architecture deepening and boundary review)
- `caveman` (ultra-terse response mode on explicit request)

## Overlap Boundaries

- Use `research` for external-source grounding; use `grill-with-docs` for decision pressure-testing against local code/contracts.
- Use `advisor` for readonly escalation when the executor is stuck on a hard fork; use `grill-with-docs` to interview the user and stress-test a plan. They are not interchangeable.
- Use `ponytail` for YAGNI / shortest-working-diff mode; use `caveman` only for ultra-terse response style. `ponytail` is not `caveman`.
- Use `general-rules` for broad engineering defaults and hook repair during `/commit`.
- Use `write-a-skill` only when the task is skill creation/refactor, not normal feature development.
- Use `general-rules` for commit/push safety flow; do not create a standalone `commit-and-push` skill, and do not duplicate full commit sequencing in command docs.
- Keep command files as entrypoints and pointers to canonical skills, not full duplicate playbooks. Ship entrypoint: `/commit` (`.cursor/commands/commit.md`).

## Skill Authoring Contract

When editing a skill, include:

1. Trigger and scope
2. Required inputs
3. Expected outputs
4. Stop and escalation rules
5. Verification checklist

## Imported Pattern Notes

- `general-rules` includes adapted diagnose/TDD/zoom-out patterns and the folded commit/push landing workflow (probe, doc sync, quality gate, clustered commits, output contract).
- `prototype` is constrained for throwaway validation; promote winners into tested slices.

## Build-Phase Skill Contract (Key Guidance)

Use `.cursor/skills/build-phase/SKILL.md` when implementing or validating build phases.

- Always distinguish build phase labels (1-8) from backend runtime checkpoint keys.
- For build-phase and orchestration edits, always read `.cursor/docs/PIPELINE.md`, `.cursor/docs/ARCHITECTURE.md`, and `.cursor/docs/IMPLEMENTATION_STATUS.md` before coding.
- Always verify `src/orchestration/resume.py` checkpoint order and frontend `RESUME_PHASE_ORDER` alignment when phase behavior changes.
- `frontend/src/lib/constants.ts` `PHASE_ORDER` may include extra UI/sub-flow phases; `RESUME_PHASE_ORDER` is the backend parity anchor.
- If endpoint or persistence parity appears to drift, stop build work and resolve contract parity first.
