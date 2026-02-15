---
name: build-phase
description: Guides the agent through implementing each build phase of the systematic review tool step-by-step. Use when implementing phases 1-8, running acceptance criteria, or determining current build phase.
---

# Build Phase Implementation

Procedural guide for implementing each build phase of the systematic review tool.

## Instructions

When the user asks to implement a build phase, follow these steps:

1. **Identify the phase** from the v2 spec (Part 5)
2. **Check prerequisites** -- verify all dependency phases are complete
3. **Read the spec** for that phase's "What to Build" section
4. **Create files** in the exact directory structure from Part 4
5. **Implement using data contracts** from Part 2 (never invent new models)
6. **Write tests** listed in Part 8 for this phase
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
| 6: Writing | Section writer, Prompts, SoF, Humanizer, style_pattern_extractor, naturalness_scorer; per-section checkpoint; naturalness >= 0.75 | test_writing_pipeline |
| 7: PRISMA/Viz | PRISMA diagram, Timeline, Geographic | test_prisma_diagram |
| 8: Export | Graph wiring, IEEE LaTeX, CLI | test_ieee_export, test_ieee_validator, test_full_review |

## Phase 6 Acceptance Criteria (updated)
- Style patterns extracted from included papers (when enabled)
- Per-section checkpoint: kill during writing, restart, picks up at next unwritten section
- Naturalness score >= 0.75 for all sections after humanization

## References
@file:docs/research-agent-v2-spec.md
