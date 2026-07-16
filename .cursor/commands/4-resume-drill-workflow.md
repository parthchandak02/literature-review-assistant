# Resume Drill Workflow

Thin launcher for operational resume/replay verification after backend or pipeline changes.

## Canonical sources

- Resume vs rerun: `.cursor/rules/core/workflow-rerun-from-snapshot-always.mdc`
- Verification gates: `.cursor/docs/IMPLEMENTATION_STATUS.md`
- PM2 restart: `.cursor/rules/core/pm2-restart-reminder-always.mdc`

## When to run

After `src/` orchestration/resume/persistence changes, or before claiming a replay fix is complete.

## Drill sequence

### 1. Pick a disposable workflow

- Choose `wf-XXXX` safe to re-run or resume.
- Confirm `<run_dir>/config_snapshot.yaml` exists; resolve `runtime.db` via `workflows_registry.db`.
- Note last completed phase and any failure point (logs or `GET /api/run/{run_id}/diagnostics`).

### 2. Restart API after backend changes

```bash
pm2 restart litreview-api
pm2 list   # confirm litreview-api is online
```

After frontend changes for production URL: `cd frontend && pnpm build && cd ..` then restart `litreview-api`.

### 3. Resume or full rerun

**Resume** (same workflow; preferred to verify a fix):

```bash
uv run python -m src.main resume --workflow-id wf-XXXX
```

**Full rerun from snapshot** (do not copy YAML into `config/review.yaml`):

```bash
uv run python -m src.main run --config <run_dir>/config_snapshot.yaml --fresh
```

Per `workflow-rerun-from-snapshot-always`: use `resume` only for the same workflow; record failing phase, fix in `src/`, re-validate with `resume`; prefer one phase earlier for safety-sensitive fixes; do not mark complete until the failing phase passes; use API-managed path for live frontend/SSE.

### 4. Release gate before claiming done

```bash
make release-check   # if target exists; else: make local-ci
```

Covers IMPLEMENTATION_STATUS verification gates (tests, endpoint parity, frontend lint/typecheck).

### 5. Workflow replay validation

```bash
uv run python scripts/validate_workflow_replay.py \
  --workflow-id wf-XXXX \
  --profile local \
  --fail-on-error
```

Optional `--db-path <runtime.db>` to bypass registry. Fixture: `tests/fixtures/replay/manifest.json`.

## Exit criteria

- Target phase(s) completed without regression.
- `make release-check` or `make local-ci` passed.
- Replay script passed with `--profile local --fail-on-error`.
- High-level changes: parity checklist in `IMPLEMENTATION_STATUS.md` before commit (`.cursor/commands/3-pre-commit-workflow.md`).
