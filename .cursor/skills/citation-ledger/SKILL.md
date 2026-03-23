---
name: citation-ledger
description: Implements citation lineage (claim -> evidence -> citation chain). Use when building src/citation/ or enforcing citation integrity.
---

# Citation Ledger Implementation

Guide for implementing the citation ledger (Phase 1 Foundation).

## Core API

- `register_claim(ClaimRecord(...))` -> claim_id
- `register_citation(CitationEntryRecord(...))` -> citation_id
- `link_evidence(EvidenceLinkRecord(...))`
- `validate_manuscript(text)` -> (unresolved_claims, unresolved_citations)
- `block_export_if_invalid()` -> bool (blocks export if any unresolved)

## Data Model

- `ClaimRecord`: claim_id, claim_text, section, confidence
- `EvidenceLinkRecord`: claim_id, citation_id, evidence_span, evidence_score
- `CitationEntryRecord`: citation_id, citekey, title, authors, resolved

## Rules

1. Every factual claim in generated text must be registered and linked to evidence
2. No export if `validate_manuscript()` returns any unresolved claims or citations
3. Citation lineage gate runs before export -- zero unresolved required

## SQLite Tables

`claims`, `evidence_links`, `citations` -- see `src/db/schema.sql` and implementations in
`src/citation/ledger.py` + repository persistence in `src/db/repositories.py`.
