---
name: ieee-export
description: Implements IEEE LaTeX export and submission packaging. Use when building export, PRISMA checklist validator, or IEEE compliance checks.
---

# IEEE Export & Submission Packaging

Guide for implementing LaTeX export and the submission package.

## IEEE LaTeX Requirements
- Use IEEEtran.cls document class
- `\cite{citekey}` numbered references
- Tables: booktabs package
- Figures: \includegraphics with proper paths
- Abstract: <= 230 words (hard cap enforced upstream before export)

## Submission Package Structure
```
submission/
|-- manuscript.tex
|-- manuscript.pdf
|-- references.bib
|-- figures/
|-- supplementary/
|   |-- search_strategies_appendix.pdf
|   |-- prisma_checklist.html
|   |-- prisma_checklist.md
|   |-- prisma_checklist.csv
|   |-- extracted_data.csv
|   |-- screening_decisions.csv
|   `-- cover_letter.md
```

## Validation Checks
- Abstract: <= 230 words
- References: warn if < 30 or > 80
- All \cite{} resolve in .bib
- No [?] or placeholder text
- PRISMA checklist >= 24/27 items reported
- Citation lineage: zero unresolved citations

## Current Artifact Reality
- Run directory artifacts include `doc_manuscript.md`, `doc_manuscript.tex`, and `references.bib` as first-class outputs.
- `POST /api/run/{run_id}/export` packages submission outputs from those run artifacts; it does not regenerate manuscript source text from scratch.
