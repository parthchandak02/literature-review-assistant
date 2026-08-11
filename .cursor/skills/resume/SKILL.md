---
name: resume
description: Operational resume/replay verification after backend or pipeline changes. Use when validating replay fixes, invoking /resume, or before claiming a workflow fix is complete.
disable-model-invocation: true
---

# Resume Drill

Operational replay verification after `src/` orchestration, resume, or persistence changes.

## Canonical sources

- Resume vs rerun: `.cursor/rules/core/rerun-workflows.mdc`
- Verification gates: `docs/TASKS.md`
- PM2 restart: `.cursor/rules/core/pm2-restart.mdc`
- Operator/WhatsApp flows: `lit-review` skill

## When to run

After backend/pipeline changes, or before claiming a replay fix is complete.

## Drill sequence

### 1. Pick a disposable workflow

- Choose `wf-XXXX` safe to re-run or resume.
- Confirm `<run_dir>/config_snapshot.yaml` exists; resolve `runtime.db` via `workflows_registry.db`.
- Note last completed phase and failure point (logs or `GET /api/run/{run_id}/diagnostics`).

### 2. Restart API after backend changes

```bash
pm2 restart litreview-api
pm2 list
```

After frontend production changes: `cd frontend && pnpm build && cd ..` then restart `litreview-api`.

### 3. Resume or full rerun

**Resume** (same workflow; preferred to verify a fix):

```bash
uv run python -m src.main resume --workflow-id wf-XXXX
```

**Full rerun from snapshot** (do not copy YAML into `config/review.yaml`):

```bash
uv run python -m src.main run --config <run_dir>/config_snapshot.yaml --fresh
```

Use `resume` only for the same workflow. Do not mark complete until the previously failing phase passes.

### 4. Release gate

```bash
make release-check   # or: make check-local
```

### 5. Workflow replay validation

```bash
uv run python scripts/check.py replay-workflow \
  --workflow-id wf-XXXX \
  --profile local \
  --fail-on-error
```

## Exit criteria

- Target phase(s) completed without regression.
- Release/local checks passed.
- Replay script passed with `--profile local --fail-on-error`.
- High-level changes: parity checklist in `docs/TASKS.md` before `commit` skill.
