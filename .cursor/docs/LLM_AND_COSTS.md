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
