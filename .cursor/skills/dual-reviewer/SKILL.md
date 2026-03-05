---
name: dual-reviewer
description: Implements dual-reviewer screening with two independent AI reviewers and adjudicator. Use when building screening logic, prompts, or reliability computation.
---

# Dual-Reviewer Screening System

Guide for implementing the core screening architecture with two independent AI reviewers and an adjudicator.

## Architecture

```
Paper -> Reviewer A (gemini-3.1-flash-lite-preview, temp=0.1, inclusion-emphasis)
      -> Reviewer B (gemini-3-flash-preview, temp=0.1, exclusion-emphasis)
         -- different model for genuine cross-model validation, not just temperature variation

If agree -> final_decision = agreed decision
If disagree -> Adjudicator (Pro tier, temp=0.2) sees both decisions -> final
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
- **Ctrl+C proceed-with-partial:** First Ctrl+C during screening exits with already-screened papers; checkpoint saved with status=partial. Second Ctrl+C aborts. DualReviewerScreener accepts `should_proceed_with_partial` callback.

## Prompt Engineering Patterns
- **Topic context injection**: Every prompt starts with Role/Goal/Backstory/Topic/Research Question/Domain/Keywords header block
- **Structured output**: All prompts end with "Return ONLY valid JSON matching this exact schema"
- **Truncation**: Title/abstract = full text; full-text = first 8,000 chars; extraction = first 10,000 chars
- **Confidence thresholds**: Auto-include >= 0.85, auto-exclude >= 0.80, between -> adjudicator

## Threshold Calibration (before main screening loop)

When `calibrate_threshold=true` (default in `ScreeningConfig`), the workflow runs a kappa-calibration
pass before the main screening loop:

1. Draw a random sample of `calibration_sample_size` papers (default 30)
2. Run `screen_batch_for_calibration()` -- always uses both reviewers (bypasses fast-path)
3. Compute Cohen's kappa; if below `calibration_target_kappa` (default 0.7), adjust thresholds via bisection
4. Repeat up to `calibration_max_iterations` (default 3) times
5. Emits `phase_start` / `phase_done` SSE events with `phase="screening_calibration"` for live UI progress
6. Skipped for living-refresh delta runs (parent_db_path set)

Key functions: `screen_batch_for_calibration(workflow_id, papers, on_progress=None)` in
`dual_screener.py`; `calibrate_threshold()` in `reliability.py`.

## References
- Screening workflow: `src/screening/dual_screener.py`
- Prompt templates: `src/screening/prompts.py`
- Reliability utilities: `src/screening/reliability.py`
