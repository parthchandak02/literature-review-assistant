---
name: quality-assessment
description: Implements risk of bias assessment (RoB 2, ROBINS-I, CASP), GRADE, and study routing. Use when building src/quality/, extraction study classifier, or traffic-light figure.
---

# Quality Assessment Implementation

Guide for implementing Phase 4 extraction and quality assessment.

## Current Maturity Note

- Current implementation uses an agentic study classifier and deterministic baseline assessors for RoB2/ROBINS-I/CASP/GRADE.
- When hardening, prefer migrating domain judgments to agentic signalling-question prompts with typed JSON outputs while preserving deterministic fallback behavior.

## Study Router

Route each paper to the correct RoB tool based on `StudyDesign`:
- RCT -> RoB 2
- Non-randomized -> ROBINS-I
- Qualitative -> CASP

## RoB 2 (RCTs) -- 5 Domains

Each domain: Low / Some concerns / High + rationale.

| Domain | Signalling Questions |
|:---|:---|
| D1 Randomization | Allocation sequence random? Concealed until enrollment? |
| D2 Deviations | Participants aware of intervention? Deviations beyond expected? |
| D3 Missing data | Outcome data for all/nearly all? Missingness depend on outcome? |
| D4 Measurement | Method appropriate? Assessment differ between groups? |
| D5 Selection | Multiple eligible measurements? Result likely selected? |

**Overall algorithm:** All Low -> Low; Any High -> High; Otherwise -> Some Concerns.

## ROBINS-I (Non-randomized) -- 7 Domains

Uses different scale: Low / Moderate / Serious / Critical / No Information.

Domains: confounding, selection, classification, deviations, missing data, measurement, reported result.

## CASP (Qualitative)

Port prompt templates from old repo. Various design-specific checklists.

## GRADE Assessor

Per-outcome assessment with all 8 factors:
- 5 downgrade: risk of bias, inconsistency, indirectness, imprecision, publication bias
- 3 upgrade: large effect, dose-response, residual confounding

Output: `GRADEOutcomeAssessment` with `final_certainty`.

## Traffic-Light Figure

`src/visualization/rob_figure.py`: rows=studies, cols=domains, cells=colored circles (matplotlib).

## Extraction Completeness Gate

Runs after extraction. Passes when >= 80% of required fields filled. Gate fails if >35% papers have empty core fields.
