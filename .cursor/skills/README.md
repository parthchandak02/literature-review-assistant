# Cursor Skills Lifecycle Map

This file maps existing skills to lifecycle stages without changing runtime behavior.
Canonical lifecycle and contract docs are under `.cursor/docs/`.

## Think

- `research`
- `protocol-generator`

## Plan

- `build-phase`
- `search-connector`
- `prototype`

## Build

- `dual-reviewer`
- `quality-assessment`
- `meta-analysis`
- `citation-ledger`
- `section-writer`
- `prisma-diagram`
- `ieee-export`

## Review and Test

- `run-database-audit`
- `general-rules`

## Ship

- `ieee-export`
- `.cursor/commands/3-pre-commit-workflow.md`

## Skill Authoring Contract

When editing a skill, include:

1. Trigger and scope
2. Required inputs
3. Expected outputs
4. Stop and escalation rules
5. Verification checklist

## Imported Pattern Notes

- `general-rules` now includes adapted engineering patterns: diagnose loop, TDD vertical slices, and zoom-out mapping.
- `prototype` is intentionally constrained for throwaway validation only; promote winners into tested production slices.
- Use `.cursor/commands/plan-to-slices.md` when converting approved plans into execution-ready slice lists.

## Build-Phase Skill Contract (Key Guidance)

Use `.cursor/skills/build-phase/SKILL.md` when implementing or validating build phases.

- Always distinguish build phase labels (1-8) from backend runtime checkpoint keys.
- For build-phase and orchestration edits, always read `.cursor/docs/PIPELINE.md`, `.cursor/docs/ARCHITECTURE.md`, and `.cursor/docs/IMPLEMENTATION_STATUS.md` before coding.
- Always verify `src/orchestration/resume.py` checkpoint order and frontend `RESUME_PHASE_ORDER` alignment when phase behavior changes.
- If endpoint or persistence parity appears to drift, stop build work and resolve contract parity first.
