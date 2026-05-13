# API Contract Overview

## Canonical API Source

`src/web/app.py` is the source of truth for implemented HTTP routes.

`frontend/src/lib/api.ts` is the source of truth for frontend API client usage.

## Endpoint Parity

Endpoint parity is enforced against `.cursor/docs/API_ENDPOINTS.md` Section `10.1 REST Endpoints` using:

- `scripts/check_spec_endpoint_parity.py`
- `tests/unit/test_spec_endpoint_parity.py`

Do not change this contract without updating tests and CI usage.

## API Domains

- Run lifecycle: `/api/run*`, `/api/stream/{run_id}`, `/api/cancel/{run_id}`
- History and registry: `/api/history*`, `/api/notes*`
- DB explorer and costs: `/api/db/{run_id}/*`, `/api/history/costs/*`
- Log and note streams: `/api/logs/stream`, `/api/notes/stream`
- Run artifacts and exports: `/api/run/{run_id}/*`
- Validation and audit: `/api/workflow/{workflow_id}/validation/*`, `/api/workflow/{workflow_id}/manuscript-audit/*`

## Contract Gotchas

- `/api/config/generate/stream` is POST, not GET.
- `/api/run` is JSON payload; CSV uploads use dedicated multipart endpoints.
- `/api/history/active-run` requires `workflow_id` query param.
- `run_id` path routes accept active run ids or `wf-*` workflow ids via resolver logic.

## SSE Surfaces

- Primary run events: `/api/stream/{run_id}`
- Notes stream: `/api/notes/stream`
- Raw process logs: `/api/logs/stream`
