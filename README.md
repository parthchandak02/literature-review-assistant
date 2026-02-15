# Systematic Review Automation Tool

Automates systematic literature reviews from research question to IEEE-submission-ready manuscripts.

## Quick Start

See `docs/research-agent-v2-spec.md` -- Part 4B for bootstrap instructions.

## What's Here

- `docs/research-agent-v2-spec.md` -- Complete build specification (single source of truth)
- `config/workflow-reference.yaml` -- Reference config from prototype (model assignments, prompts, thresholds)
- `.cursor/rules/` -- 11 Cursor rules for development guardrails
- `.cursor/skills/` -- 11 Cursor skills for subsystem implementation
- `.env` -- API keys (not committed, create from Part 6.3 of the spec)

## Build Order

Phase 1: Foundation -> Phase 2: Search -> Phase 3: Screening -> Phase 4: Extraction/Quality ->
Phase 5: Synthesis -> Phase 6: Writing -> Phase 7: PRISMA/Viz -> Phase 8: Export/Orchestration
