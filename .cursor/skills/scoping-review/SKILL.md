---
name: scoping-review
description: JBI/PRISMA-ScR scoping review methodology for literature-review-assistant. Phase 1 is config-only; full pipeline in Phases 2-6.
---

# scoping-review

## Phase 1 status (current)

- Users choose scoping vs systematic via decision wizard
- Generated YAML includes `review_type: scoping`, `question_framework: pcc`, and `pcc` fields
- `resolve_profile()` returns scoping methodology flags (OSF, PRISMA-ScR, no GRADE/meta-analysis by default)
- **Pipeline still SR-shaped** until Phase 2+ — do not claim end-to-end scoping runs work yet

## Key files

- `src/models/methodology_profile.py` — `resolve_profile()`
- `src/models/config.py` — `PCCConfig`, `question_framework`
- `tests/fixtures/scoping/review_scoping_smoke.yaml`

## Verification

```bash
uv run python scripts/check.py config-methodology
uv run python .cursor/skills/verify-litreview/control_litreview.py phase1-gate --json
```

## Scientific guardrails

- Scoping maps evidence; does not conclude intervention effectiveness
- PCC (Population, Concept, Context) not PICO
- PRISMA-ScR reporting (Phase 4), not PRISMA 2020
- Optional critical appraisal only when justified

## References

- Dr. Chandak scoping vs systematic tables (project plan)
- `.cursor/rules/domain/review-methodology.mdc` (extend for scoping in Phase 2)
