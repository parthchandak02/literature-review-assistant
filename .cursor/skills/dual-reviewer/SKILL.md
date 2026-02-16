---
name: dual-reviewer
description: Implements dual-reviewer screening with two independent AI reviewers and adjudicator. Use when building screening logic, prompts, or reliability computation.
---

# Dual-Reviewer Screening System

Guide for implementing the core screening architecture with two independent AI reviewers and an adjudicator.

## Architecture

```
Paper -> Reviewer A (Flash-Lite, temp=0.1, inclusion-emphasis)
      -> Reviewer B (Flash-Lite, temp=0.3, exclusion-emphasis)
      
If agree -> final_decision = agreed decision
If disagree -> Adjudicator (Pro, temp=0.2) sees both decisions -> final
```

## Implementation Steps

1. Create PydanticAI agents for Reviewer A, B, and Adjudicator
2. Each reviewer returns `ScreeningDecision` with decision, reason, exclusion_reason, confidence
3. Compare decisions -- if agreement, log and return
4. If disagreement, invoke adjudicator with both decisions + reasoning
5. Log ALL individual decisions to `screening_decisions` table (per-paper, immediately)
6. Log final result to `dual_screening_results` table
7. Compute Cohen's kappa after each stage using sklearn
8. Generate disagreements_report.md

## Critical Rules
- Two-stage: title/abstract first, then full-text for survivors
- Full-text stage requires PDF retrieval first (Unpaywall / open access)
- Every EXCLUDED paper at full-text stage must have `ExclusionReason` enum value
- Paper-level checkpoint: save each decision to SQLite immediately (not batch)

## Prompt Engineering Patterns
- **Topic context injection**: Every prompt starts with Role/Goal/Backstory/Topic/Research Question/Domain/Keywords header block
- **Structured output**: All prompts end with "Return ONLY valid JSON matching this exact schema"
- **Truncation**: Title/abstract = full text; full-text = first 8,000 chars; extraction = first 10,000 chars
- **Confidence thresholds**: Auto-include >= 0.85, auto-exclude >= 0.80, between -> adjudicator

## References
- Screening workflow: `src/screening/dual_screener.py`
- Prompt templates: `src/screening/prompts.py`
- Reliability utilities: `src/screening/reliability.py`
