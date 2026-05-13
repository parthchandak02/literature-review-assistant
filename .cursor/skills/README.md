# Cursor Skills Lifecycle Map

This file maps existing skills to lifecycle stages without changing runtime behavior.
Canonical lifecycle and contract docs are under `.cursor/docs/`.

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

- `protocol-generator`
- `search-connector`
- `prototype`
- `citation-ledger` (lineage reference; primary writing flow lives in `section-writer`)

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
