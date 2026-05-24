# Cursor Skills Lifecycle Map

This file maps existing skills to lifecycle stages without changing runtime behavior.
Canonical lifecycle and contract docs are under `.cursor/docs/`.

## Canonical Ownership Matrix

Use one canonical skill per workflow area. Adjacent skills should point back to the owner instead of duplicating full procedures.

| Workflow Area | Canonical Skill | Secondary Skill(s) | Notes |
|---|---|---|---|
| Session bootstrap + orientation | `general-rules` | `build-phase`, `research` | `general-rules` owns reusable startup/process defaults; lifecycle routing still comes from `.cursor/docs/INDEX.md`. |
| Commit/push hygiene | `general-rules` | `setup-pre-commit` | `general-rules` owns commit workflow behavior; `setup-pre-commit` owns hook installation only. |
| Hook/bootstrap automation | `setup-pre-commit` | `general-rules` | Keep setup mechanics here; avoid repeating commit policy. |
| Skill authoring and de-duplication | `write-a-skill` | `general-rules` | `write-a-skill` owns skill structure/workflow; `general-rules` only provides global constraints. |
| External research grounding | `research` | `grill-with-docs` | `research` owns source-backed discovery; `grill-with-docs` owns plan pressure-testing. |
| Plan pressure-testing | `grill-with-docs` | `research` | Use code/docs contradiction checks and decision-tree questioning here. |
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

## Specialist / Optional Skills

- `lit-review` (runtime operator playbook; lives at `skills/lit-review` and is linked into `.cursor/skills/lit-review`)
- `protocol-generator`
- `search-connector`
- `prototype`
- `citation-ledger` (lineage reference; primary writing flow lives in `section-writer`)
- `setup-pre-commit` (repo commit-hook setup and verification workflow)

## Collaboration / Meta Skills

- `grill-with-docs` (one-question-at-a-time plan pressure testing against repo contracts)
- `handoff` (compact transfer package for next-agent continuation)
- `write-a-skill` (skill authoring, tailoring, and de-duplication workflow)
- `caveman` (ultra-terse response mode on explicit request)

## Overlap Boundaries

- Use `research` for external-source grounding; use `grill-with-docs` for decision pressure-testing against local code/contracts.
- Use `general-rules` for broad engineering defaults; use `setup-pre-commit` only for hook bootstrap/repair work.
- Use `write-a-skill` only when the task is skill creation/refactor, not normal feature development.
- Use `general-rules` for commit/push safety flow; do not duplicate full commit sequencing in command docs.
- Keep command files as entrypoints and pointers to canonical skills, not full duplicate playbooks.

## Skill Authoring Contract

When editing a skill, include:

1. Trigger and scope
2. Required inputs
3. Expected outputs
4. Stop and escalation rules
5. Verification checklist

## Imported Pattern Notes

- `general-rules` includes adapted diagnose/TDD/zoom-out patterns.
- `prototype` is constrained for throwaway validation; promote winners into tested slices.

## Build-Phase Skill Contract (Key Guidance)

Use `.cursor/skills/build-phase/SKILL.md` when implementing or validating build phases.

- Always distinguish build phase labels (1-8) from backend runtime checkpoint keys.
- For build-phase and orchestration edits, always read `.cursor/docs/PIPELINE.md`, `.cursor/docs/ARCHITECTURE.md`, and `.cursor/docs/IMPLEMENTATION_STATUS.md` before coding.
- Always verify `src/orchestration/resume.py` checkpoint order and frontend `RESUME_PHASE_ORDER` alignment when phase behavior changes.
- `frontend/src/lib/constants.ts` `PHASE_ORDER` may include extra UI/sub-flow phases; `RESUME_PHASE_ORDER` is the backend parity anchor.
- If endpoint or persistence parity appears to drift, stop build work and resolve contract parity first.
