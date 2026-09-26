# Jev (TypeSafe System One) — verified reference for this repo

Sources: `~/.hermes/skills/jev-decision-model/SKILL.md`, `references/use-case-status.md`,
`~/.hermes/skills/research/tool-evaluation-research/references/typesafe-jev-integration.md`,
jobwright `src/jobwright/scoring/fastpath.py` (reference shadow-mode implementation).

## Live probe (2026-09-26)

- `POST https://api.typesafe.ai/v1/systemone` with the operator's TypeSafe bearer token
  (Hermes operator env), model pinned `jev-1.13.0`.
- 3-paper title/abstract screening fan-out (one `choice` question per paper, anchored
  "For paper #N"): INCLUDE 0.98 / EXCLUDE 1.0 / EXCLUDE 1.0, all correct. 0.18 s,
  683 input / 135 output tokens. Response has no `usage.cost`; price from tokens.

## What Jev is

Decision classifier: `{model, state, questions}` in, typed answers + probabilities out.
Cannot generate or transform prose. Question types (questions are a named record):

- `noul`: `{"type": "noul", "instructions": ...}` (structured form: `criteria.true/false`
  with `what` + `examples`) -> `{noul: p_yes}` or `probabilities.true`. No confidence field;
  noul(X) + noul(not X) need not sum to 1 — use one-directional thresholds.
- `choice`: `criteria` is a record `{LABEL: description}` -> `{choice, probabilities, confidence}`.
- `score`: `criteria` is an ARRAY (ordered rubric) -> `{score (float, 0-indexed), probabilities, confidence}`.

## Limits and economics

- Effective context ≈ state + longest single question ≈ 32K tokens (≈33.6K -> HTTP 400).
- Fan-out: N questions over one state pay the state once; latency grows with N
  (13 q ≈ 0.3 s, 48 q ≈ 13 s). 1,200 rpm / 250K tok/s. No batch API, no caching.
- Every fan-out question must anchor its item ("For paper #3: ...") or answers collapse.
- English-primary.

## Hard rules adopted for this repo

1. Three-state config per surface: `off | shadow | on`, default `off`.
2. Shadow first: Jev runs alongside the incumbent LLM path, answers persisted, zero behavior
   change. Flip to `on` only after agreement stats on real runs + user approval.
3. Confidence routing: act only above a per-surface calibrated threshold (start >= 0.85 for
   anything that excludes a paper); everything else escalates to the incumbent LLM path.
4. Fail-open: any Jev error/timeout/missing key -> incumbent path, never blocks the phase.
5. Never used for prose, statistics, or anything >32K tokens.
6. Model id lives in `config/settings.yaml`, never hardcoded; every call logs to `cost_records`.
7. Confidence is normalized max-probability, not learned calibration — calibrate per task
   from shadow data (bias direction is task-specific).
