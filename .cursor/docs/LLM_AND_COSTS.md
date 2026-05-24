# LLM and Cost Contract

## Model Configuration

All model ids are configured in `config/settings.yaml`.
Do not hardcode provider model strings in code.

## LLM Invocation Pattern

- Use typed output validation for structured LLM responses.
- Use provider rate limiter reservations before high-cost model calls.
- Persist call accounting into `cost_records`.

## Cost Surfaces

- Per-run costs: `/api/db/{run_id}/costs`, `/api/db/{run_id}/costs/aggregates`, `/api/db/{run_id}/costs/export`
- Global cost history: `/api/history/costs/aggregates`, `/api/history/costs/export`

## Time Filter Rule

Cost aggregate/export filters use stored `created_at` in `cost_records`.
Do not assume downstream aggregations use any client-side timestamp.

## Screening Cost Controls

Screening and pre-ranking knobs in `config/settings.yaml` and review config drive largest cost variance.
Changes must be documented with expected effect on paper-throughput versus LLM-call volume.

### Screening Funnel Order

Screening cost is controlled by a fixed funnel:

1. BM25 ranks candidate papers by relevance.
2. `max_llm_screen` caps how many papers can enter LLM screening.
3. `batch_screen_*` pre-ranks BM25-selected papers in groups (`batch_screen_size`).
4. Only forwarded papers enter dual-reviewer screening (`reviewer_batch_size` controls call packing).

This means throughput and spend depend on all four stages, not one knob in isolation.

### Current Baseline Defaults (Recall-first)

From `config/settings.yaml`:

- `max_llm_screen: 200`
- `batch_screen_enabled: true`
- `batch_screen_size: 80`
- `batch_screen_threshold: 0.30`
- `batch_screen_concurrency: 3`
- `reviewer_batch_size: 10`
- `screening_concurrency: 5`

This profile prioritizes recall while still reducing dual-reviewer call count through batch pre-ranking and reviewer batching.

### Preset Profiles (copy/paste into `screening:` block)

Use these as documented operating profiles. Do not switch to a stricter threshold without replay validation.

Recall-first (default):

```yaml
screening:
  max_llm_screen: 200
  batch_screen_enabled: true
  batch_screen_size: 80
  batch_screen_threshold: 0.30
  batch_screen_uncertain_band: 0.10
  batch_screen_concurrency: 3
  reviewer_batch_size: 10
  screening_concurrency: 5
```

Balanced economy (after replay validation):

```yaml
screening:
  max_llm_screen: 200
  batch_screen_enabled: true
  batch_screen_size: 80
  batch_screen_threshold: 0.35
  batch_screen_uncertain_band: 0.10
  batch_screen_concurrency: 3
  reviewer_batch_size: 10
  screening_concurrency: 5
```

Exploratory cap (fast/cheap dry runs):

```yaml
screening:
  max_llm_screen: 100
  batch_screen_enabled: true
  batch_screen_size: 80
  batch_screen_threshold: 0.30
  batch_screen_uncertain_band: 0.10
  batch_screen_concurrency: 3
  reviewer_batch_size: 10
  screening_concurrency: 5
```

### Validation Guidance

- Raising `batch_screen_threshold` can reduce calls but increases false-exclusion risk.
- Any threshold increase above `0.30` should be validated with workflow replay before production use.
- Keep `reviewer_batch_size: 10` unless there is a clear quality or debugging reason to use per-paper mode.

### Optional SQL Check (cost attribution sanity check)

For a completed workflow, verify screening savings by grouping `cost_records` by `phase`:

```sql
SELECT phase, COUNT(*) AS calls, ROUND(SUM(cost_usd), 4) AS usd
FROM cost_records
WHERE workflow_id = ?
GROUP BY phase
ORDER BY usd DESC;
```
