---
name: lit-review
description: High-precision guide for running systematic reviews with the literature-review-assistant repo using low-iteration, low-token operations after kickoff.
version: 1.4.0
author: Hermes Agent
platforms: [macos, linux]
metadata:
  hermes:
    tags: [literature-review, systematic-review, PRISMA, research, commands, LaTeX]
---

# Systematic Literature Review Pipeline (lit-review)

This is a high-precision, production-grade guide for any AI agent (or developer) to operate `literature-review-assistant` and execute systematic reviews with minimal Hermes iteration burn.

---

## One-time setup (do this first)

1. Clone: `git clone https://github.com/parthchandak/literature-review-assistant.git`
2. Install deps: `cd literature-review-assistant && uv sync`
3. Set root: `export LITREVIEW_ROOT="$PWD"`
4. Link skill: `./scripts/link-hermes-skill.sh`
5. Configure keys: copy `.env.example` to `.env` and set required API keys.
6. Verify CLI: `uv run python -m src.main --help`

Hermes usage:

- Attach `lit-review` (`/lit-review`) and run from the cloned repo.
- Do not duplicate this skill under `~/.hermes` manually; keep it symlinked.
- Distribution note: `uvx` packaging is intentionally deferred; this skill assumes a local clone + `uv sync`.

---

## 📂 Key Paths & Files
* `src/main.py`: CLI entrypoint.
* `src/web/config_generator.py`: Two-stage LLM configuration generator.
* `scripts/start_review.py`: Question to `review.yaml` generator.
* `scripts/watch_review.py`: One-shot or follow-mode workflow monitor.
* `scripts/link-hermes-skill.sh`: Idempotent symlink setup helper.
* `config/review.yaml`: Target systematic review configuration (PICO, keywords, criteria, databases).
* `config/settings.yaml`: LLM models, agents, and cost fallback settings.
* `runs/`: Directory where all runs, databases (`runtime.db`), and manuscript drafts are saved.
* `runs/workflows_registry.db`: Canonical workflow registry for workflow ID to db_path lookup.

---

## Low-cost operating contract (must follow)

- Max Hermes agent involvement for one run:
  - Config generation: once
  - Start or resume: once
  - Validate/export at terminal phase: once each
- After kickoff, monitor with scripts or no-agent cron only.
- Do not poll status in an interactive chat loop.
- Do not patch `runs/` artifacts.
- Resume from run snapshots (`config_snapshot.yaml`) for replay-safe reruns.

---

## 💻 Step-by-step execution playbook

### Step 1: Generate configuration (`review.yaml`)

If `config/review.yaml` does not exist yet, generate it:
```bash
python "$LITREVIEW_ROOT/scripts/start_review.py" --question "YOUR RESEARCH QUESTION"
```

Optional:

- `--profile`: `standard` (default) or `health_sdg`
- `--output`: path to write YAML (default: `config/review.yaml`)

### Step 2: Launch the Review Workflow

Start in background for long runs to avoid interactive iteration burn:
```bash
uv run python -m src.main run --fresh
```
The pipeline handles search, deduplication, dual screening, extraction, quality, synthesis, writing, and finalize.

### Step 3: Monitor without burning iterations

One-shot status checks:
```bash
uv run python -m src.main status --workflow-id <id>
python "$LITREVIEW_ROOT/scripts/watch_review.py" --workflow-id <id>
```

Follow major stage events:
```bash
python "$LITREVIEW_ROOT/scripts/watch_review.py" --workflow-id <id> --follow
```

Optional live API stream for humans:
```bash
curl -N "http://localhost:8001/api/logs/stream?workflow_id=<id>"
```

### Step 4: Resume (as needed)

If interrupted or failed:
```bash
uv run python -m src.main resume --workflow-id <id>
uv run python -m src.main resume --workflow-id <id> --from-phase phase_5_synthesis
```

### Step 5: Validate and export
```bash
uv run python -m src.main validate --workflow-id <id>
uv run python -m src.main export --workflow-id <id>
```
Outputs are saved under `runs/.../submission/`.

---

## No-agent cron template (recommended)

Use Hermes `cronjob` with `no_agent=True` and a script-based monitor. This avoids model invocations when no stage change happened.

Prompt template for Hermes:

> Every 10 minutes run `python "$LITREVIEW_ROOT/scripts/watch_review.py" --workflow-id wf-XXXX` and deliver output only when non-empty. Use no-agent mode.

Expected behavior:

- Empty stdout: silent tick
- Non-empty stdout: status/phase message delivered
- Non-zero exit: error alert delivered

See [references/hermes-monitoring.md](references/hermes-monitoring.md) for full examples.

---

## Critical constraints and pitfalls

- Use pipeline-generated writing outputs; do not draft sections manually in chat while a run is active.
- Never invent citekeys; citations must come from run artifacts.
- Normalize accented surnames for citekey lookups (for example, `Pérez-Encinas` to `Perez-Encinas`).
- Avoid SVG-only figure pipelines for LaTeX packaging; include PNG/PDF outputs.
- Respect scholarly API rate limits and backoffs.
