---
name: section-writer
description: Implements manuscript section writing with citation lineage. Use when building section writer, humanizer, or citation ledger integration.
---

# Manuscript Section Writing

Guide for implementing the section writer with full citation lineage enforcement.

## Per-Section Requirements

### Abstract (<= 230 words)
Must cover all 12 PRISMA 2020 abstract items:
1. Title -- identify as systematic review/meta-analysis
2. Objectives -- research question with PICO
3. Eligibility criteria
4. Information sources with dates
5. Risk of bias methods
6. Included studies count/characteristics
7. Synthesis results with CIs
8. Key findings
9. Strengths and limitations
10. Registration/funding
11. Protocol registration number
12. Funding sources

### Methods (PRISMA Items 3-16)
Must cover: eligibility criteria, information sources, search strategy (reference appendix), selection process (dual reviewer + kappa), data collection, data items, RoB tools, effect measures, synthesis methods, GRADE.

### Results
Must reference: PRISMA diagram, study characteristics table, RoB traffic-light figure, forest plot, GRADE SoF table.

### Discussion
Key findings, comparison with prior work, strengths, limitations, implications.

## Citation Lineage Workflow
For each claim in generated text:
1. `CitationLedger.register_claim(claim_text, section, confidence)`
2. `CitationLedger.link_evidence(claim_id, citation_id, evidence_span, score)`
3. After section complete: `CitationLedger.validate_section()` -- zero unresolved claims
4. Export blocks if any claim lacks evidence chain

## Humanization and Guardrails
- `src/writing/humanizer_guardrails.py` performs deterministic cleanup before/after humanization
- Guardrails must preserve bracketed citekeys and numeric/statistical tokens
- If protected token integrity changes, fallback returns original text

## Writing Prompt Patterns (every section)

### Prohibited Phrases
NEVER use: "Of course", "Here is", "As an expert", "Certainly", "In this section", "As mentioned above", "It is important to note", "It should be noted". No conversational preamble. No separator lines (***, ---). Output suitable for direct insertion.

### Citation Catalog Constraint
Use ONLY citations from the provided catalog. Use exact citekey format: [Smith2023], [Jones2024a]. Do NOT invent citations. Every factual claim must be supported by at least one citation.

### Study-Count Adaptation
- 0 studies: error state
- 1 study: singular language, no synthesis/comparison subsections
- 2+ studies: plural language, full synthesis subsections

### Truncation Limits
- Title/abstract screening input: full title + abstract (no truncation)
- Full-text screening input: first 8,000 chars
- Data extraction input: first 32,000 chars
- Humanization input should preserve citations and numeric values; do not truncate in ways that clip citekeys
