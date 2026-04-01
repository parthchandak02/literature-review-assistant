---
name: build-phase
description: Guides the agent through implementing each build phase of the systematic review tool step-by-step. Use when implementing phases 1-8, running acceptance criteria, or determining current build phase.
---

# Build Phase Implementation

Procedural guide for implementing each build phase of the systematic review tool.

## Instructions

When the user asks to implement a build phase, follow these steps:

1. **Identify the phase** from `spec.md` and current `src/` modules
2. **Check prerequisites** -- verify all dependency phases are complete
3. **Read the spec** for that phase's implementation and acceptance details
4. **Create files** in the current project directory structure
5. **Implement using typed data contracts** from `src/models/` (never invent untyped boundaries)
6. **Write tests** that match the current test suite naming
7. **Run acceptance criteria** -- every checkbox must pass
8. **Report results** to user before proceeding

## Phase Quick Reference

| Phase | Key Deliverables | Test Files |
|:---|:---|:---|
| 1: Foundation | Models, SQLite, Gates, Ledger, LLM Provider | test_models, test_database, test_gates, test_citation_ledger |
| 2: Search | Connectors, Strategy, Dedup, Protocol | test_protocol |
| 3: Screening | Dual-reviewer, Prompts, Kappa | test_screening, test_reliability, test_dual_screening |
| 4: Extraction | Extractor, RoB2, ROBINS-I, CASP, GRADE | test_rob2, test_robins_i, test_quality_pipeline |
| 5: Synthesis | Effect sizes, Meta-analysis, Forest/Funnel | test_effect_size, test_meta_analysis, test_synthesis_pipeline |
| 6: Writing | Section writer, prompts, SoF, humanizer guardrails, citation grounding, prior-section context chaining; abstract limit follows `settings.ieee_export.max_abstract_words` with deterministic trim headroom/floor | test_writing_pipeline |
| 7: PRISMA/Viz | PRISMA diagram, Timeline, Geographic | test_prisma_diagram |
| 8: Export | Graph wiring, IEEE LaTeX, submission packaging, CLI, resume, workflow_registry | test_export, test_workflow_registry, test_resume_state, integration export/api tests |

## Phase 6 Acceptance Criteria (updated)
- Per-section persistence: interrupted runs can resume writing without losing completed sections
- Discussion and conclusion use prior-sections context rather than repeating earlier sections
- Abstract is deterministically trimmed using runtime settings:
  - target: `max(ieee_export.max_abstract_words - writing.abstract_trim_headroom_words, writing.abstract_trim_floor_words)`
  - contract ceiling: `ieee_export.max_abstract_words` (default 250)

## References
@file:spec.md
