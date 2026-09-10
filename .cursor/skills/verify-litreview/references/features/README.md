# Feature Map — Setup & Config (Phase 1)

Materialized memory for agents verifying scoping vs systematic review setup.

## Sub-features

| Feature | File | User POV |
|---------|------|----------|
| Review type wizard | `review-type-decision-wizard.md` | Choose scoping vs systematic before question |
| Question + generate | `setup-config-generation.md` | Enter question, generate YAML |
| Methodology profile | `methodology-profile.md` | Resolved flags from `review_type` |

## Verification CLI

```bash
uv run python .cursor/skills/verify-litreview/control_litreview.py phase1-gate --json
uv run python scripts/check.py config-methodology
```

## Gotchas

- Phase 1 is **config-only**: scoping YAML is valid but pipeline still runs SR phases until Phase 2+.
- Config generator previously forced `review_type: systematic`; now respects wizard choice.
- Scoping fixture: `tests/fixtures/scoping/review_scoping_smoke.yaml`
