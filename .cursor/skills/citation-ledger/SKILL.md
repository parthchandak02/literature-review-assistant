---
name: citation-ledger
description: Implements citation lineage (claim -> evidence -> citation chain). Use when building src/citation/ or enforcing citation integrity.
---

# Citation Ledger Implementation

Lean reference for citation lineage boundaries. Primary writing-lineage workflow now lives in `section-writer/SKILL.md`.

## Canonical Sources

- Runtime implementation: `src/citation/ledger.py`
- Persistence: `src/db/schema.sql`, `src/db/repositories.py`
- Writing integration and section-level lineage checks: `.cursor/skills/section-writer/SKILL.md`

## Non-Negotiables

1. Every factual claim must map to evidence and citation lineage.
2. Export must fail when unresolved lineage remains.
3. Numeric `[N]` citations are valid only when they map to known references post-conversion.
