---
name: build-phase
description: Guides the agent through implementing each build phase of the systematic review tool step-by-step. Use when implementing phases 1-8, running acceptance criteria, or determining current build phase.
---

# Build Phase Implementation

Procedural guide for implementing each build phase of the systematic review tool.

## Instructions

When the user asks to implement a build phase, follow these steps:

1. **Identify the phase** from `.cursor/docs/PIPELINE.md` and current `src/` modules
2. **Check prerequisites** -- verify all dependency phases are complete
3. **Read the contract docs** for that phase's implementation and acceptance details
4. **Create files** in the current project directory structure
5. **Implement using typed data contracts** from `src/models/` (never invent untyped boundaries)
6. **Write tests** that match the current test suite naming
7. **Run acceptance criteria** -- every checkbox must pass
8. **Report results** to user before proceeding

## Trigger and Scope

- Trigger: user asks for phase implementation, phase status, or acceptance checks.
- Scope: build-phase planning and implementation alignment only; do not rewrite unrelated modules.

## Required Inputs

- `.cursor/docs/PIPELINE.md`
- `.cursor/docs/IMPLEMENTATION_STATUS.md`
- `.cursor/docs/ARCHITECTURE.md`
- Relevant domain skill docs in `.cursor/skills/**/SKILL.md`

## Expected Outputs

- Clear phase mapping to runtime checkpoint keys
- File-level implementation summary
- Test command results and acceptance verdict

## Stop Conditions and Escalation

- Stop and ask user when a required dependency phase is missing.
- Stop and ask user when acceptance criteria conflict with current runtime contracts.
- Escalate when endpoint or persistence parity constraints fail.

## Verification Checklist

- Runtime checkpoint alignment verified (`src/orchestration/resume.py`)
- Frontend resume order alignment verified (`frontend/src/lib/constants.ts`)
- Relevant tests run for changed modules
- Contract docs updated when behavior changed

## Phase Quick Reference

| Phase | Key Deliverables | Test Files |
|:---|:---|:---|
| 1: Foundation | Models, SQLite, Gates, Ledger, LLM Provider | test_models, test_database, test_gates, test_citation_ledger |
| 2: Search | Connectors, Strategy, Dedup, Protocol | test_protocol |
| 3: Screening | Dual-reviewer, Prompts, Kappa | test_screening, test_reliability, test_dual_screening |
| 4: Extraction | Extractor, RoB2, ROBINS-I, CASP, GRADE | test_rob2, test_robins_i, test_quality_pipeline |
| 5: Synthesis | Effect sizes, Meta-analysis, Forest/Funnel | test_effect_size, test_meta_analysis, test_synthesis_pipeline |
| 6: Writing | Section outline generation, ratchet-scored section rewrites, section writer, prompts, SoF, humanizer guardrails, citation grounding, prior-section context chaining; abstract limit follows `settings.ieee_export.max_abstract_words` with deterministic trim headroom/floor | test_writing_pipeline, test_structured_writing, test_writing_pipeline_fixes, test_outline_generator, test_section_quality_score |
| 7: PRISMA/Viz | PRISMA diagram, Timeline, Geographic | test_prisma_diagram |
| 8: Export | Graph wiring, IEEE LaTeX, submission packaging, CLI, resume, workflow_registry | test_export, test_workflow_registry, test_resume_state, integration export/api tests |

Naming note: build-phase numbering (1-8) is not the same as runtime checkpoint
key names. The orchestration graph includes `phase_5c_pre_writing_gate`
between knowledge-graph and writing, plus the post-writing checkpoint
`phase_7_audit` before `finalize` in `src/orchestration/resume.py`. Keep
discussion of build "Phase 7: PRISMA/Viz" separate from runtime
`phase_7_audit`.

When validating runtime phase coverage after synthesis/writing changes, include
`tests/unit/test_pre_writing_gate.py` and confirm
`frontend/src/lib/constants.ts` `RESUME_PHASE_ORDER` still matches backend
`PHASE_ORDER`.
Only `RESUME_PHASE_ORDER` is the backend resume-order contract. Frontend `PHASE_ORDER`
may include additional UI/sub-flow entries and should not be forced to mirror backend
`PHASE_ORDER` one-to-one.

## Phase 6 Acceptance Criteria (updated)
- Per-section persistence: interrupted runs can resume writing without losing completed sections
- Outline persistence: `phase_6a2_outline` + `section_outlines` are reused on resume and cleared when rewinding from `phase_6_writing`
- Ratchet loop is bounded: quality improves lexicographically or stops on plateau, duplicate fingerprint, deterministic fallback, or cost budget
- Discussion and conclusion use prior-sections context rather than repeating earlier sections
- Abstract is deterministically trimmed using runtime settings:
  - target: `max(ieee_export.max_abstract_words - writing.abstract_trim_headroom_words, writing.abstract_trim_floor_words)`
  - contract ceiling: `ieee_export.max_abstract_words` (default 250)

## References
@file:.cursor/docs/PIPELINE.md
@file:.cursor/docs/IMPLEMENTATION_STATUS.md
