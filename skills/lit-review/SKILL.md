---
name: lit-review
description: High-precision guide for running systematic reviews with the literature-review-assistant repo using low-iteration, low-token operations after kickoff.
version: 1.7.0
author: Hermes Agent
platforms: [macos, linux]
metadata:
  hermes:
    tags: [literature-review, systematic-review, PRISMA, research, commands, LaTeX]
---

# Systematic Literature Review Pipeline (lit-review)

This is a high-precision, production-grade guide for any AI agent (or developer) to operate `literature-review-assistant` and execute systematic reviews with minimal Hermes iteration burn.

---

## Repo location (this machine)

**REPO_ROOT:** `~/projects/literature-review-assistant/`
All commands below must be run from this directory (or use `LITREVIEW_ROOT`).

The repo is already cloned, `uv sync`'d, and local credentials are configured per the example template.  
Review `config/settings.yaml` to see which LLM models are assigned to each stage.

## One-time setup on a fresh machine

1. `git clone https://github.com/parthchandak02/literature-review-assistant.git`
2. `cd literature-review-assistant && uv sync`
3. Copy the example environment file to the project root and fill in required keys (see example template comments)
4. Verify: `uv run python -m src.main --help`
5. Hermes host: `nvm alias default 20.19.2` and run `scripts/hermes-maintain.sh` once (see `references/hermes-monitoring.md`)

---

## Key Paths & Files
* `src/main.py`: CLI entrypoint.
* `src/web/config_generator.py`: Two-stage LLM configuration generator.
* `scripts/start_review.py`: Question -> `config/review.yaml` generator. Usage: `uv run python scripts/start_review.py --question "..."`.
* `scripts/watch_review.py`: One-shot or follow-mode workflow monitor. Outputs status line only when state changes (use for quick checks). Usage: `uv run python scripts/watch_review.py --workflow-id wf-NNNN`.
* `scripts/stream_review_whatsapp.py`: Long-running WhatsApp progress stream (one editable bubble per phase). Requires `--chat-id` from the group where the user started the review. Usage: `python scripts/stream_review_whatsapp.py --workflow-id wf-NNNN --chat-id '<jid>'` (use the Hermes agent venv if needed).
* `~/.hermes/scripts/whatsapp_stream.py`: Shared Hermes bridge client (`send` / `edit` / `send_media`) for any local script.
* `scripts/show_run_info.py`: Print run metadata (status, included papers, cost) for a workflow ID. Usage: `uv run python scripts/show_run_info.py --workflow-id wf-NNNN`.
* `config/review.yaml`: Target systematic review configuration (PICO, keywords, criteria, databases) — overwritten each time `start_review.py` runs.
* `config/settings.yaml`: LLM models, agents, and cost fallback settings.
* `runs/`: Directory where all runs, databases (`runtime.db`), and manuscript drafts are saved.
* `runs/workflows_registry.db`: Canonical workflow registry for workflow ID to db_path lookup.

---

## Low-cost operating contract (must follow)

- Max Hermes agent involvement for one run:
  - Config generation: once
  - Start or resume: once
  - Validate/export at terminal phase: once each
- After kickoff, check progress only when the user asks or at natural breakpoints. Reviews are one-off (20-60 min) — no cron needed.
- Do NOT set up recurring cron jobs for status monitoring. Reviews are not daily recurring tasks.
- Do not patch `runs/` artifacts.
- Resume from run snapshots (`config_snapshot.yaml`) for replay-safe reruns.

---

## Pipeline phases (timing estimate)

Typical review runs through these phases – 20-60 min total:

| Phase | What happens | Est. time |
|-------|-------------|-----------|
| 1. Start | Load config, init DB, register workflow ID | ~30s |
| 2. Search | Run connectors, deduplicate, generate protocol | 2-5 min |
| 3. Screening | Dual LLM review of all papers | 10-20 min |
| 4. Extraction | Data extraction + quality assessment (RoB, GRADE) | 5-15 min |
| 5. Synthesis | Meta-analysis or narrative synthesis | 5-10 min |
| 6. Writing | Section generation + manuscript assembly | 5-10 min |
| Finalize | Generate references, BibTeX, LaTeX | ~1 min |

## Quick health-check queries (runtime.db)

For precise progress, query the runtime.db directly:

```bash
sqlite3 runs/YYYY-MM-DD/wf-NNNN-*/run_*/runtime.db "SELECT phase_label, status FROM workflow_steps ORDER BY id DESC LIMIT 1;"
sqlite3 runs/YYYY-MM-DD/wf-NNNN-*/run_*/runtime.db "SELECT COUNT(*) FROM screening_decisions;"
sqlite3 runs/YYYY-MM-DD/wf-NNNN-*/run_*/runtime.db "SELECT COUNT(*) FROM extraction_records;"
sqlite3 runs/YYYY-MM-DD/wf-NNNN-*/run_*/runtime.db "SELECT COUNT(*) FROM section_drafts;"
```

---

## Step-by-step execution playbook

### Step 1: Generate configuration (`config/review.yaml`)

```bash
cd ~/projects/literature-review-assistant
uv run python scripts/start_review.py --question "YOUR RESEARCH QUESTION"
```

Optional: `--profile standard` (default) or `health_sdg`

Review the `pico`, `keywords`, `inclusion_criteria`, and `search_overrides` before launching.

### Step 2: Launch in tmux

Reviews take 20-60+ minutes. Launch in a tmux session:

```bash
cd ~/projects/literature-review-assistant
tmux new-session -d -s litreview 'uv run python -m src.main run --config config/review.yaml 2>&1 | tee /tmp/litreview-output.log; sleep 9999'
```

Capture the **workflow ID** from startup output.

### Step 2b: Stream progress to WhatsApp (recommended)

Hermes must pass the **current group's** WhatsApp JID (`HERMES_SESSION_CHAT_ID`) into the streamer — detached tmux does not inherit session env.

```bash
CHAT_ID='<paste HERMES_SESSION_CHAT_ID from this group>'
cd ~/projects/literature-review-assistant
tmux new-session -d -s litreview-wa \
  "python scripts/stream_review_whatsapp.py \
  --workflow-id wf-NNNN --chat-id \"$CHAT_ID\" --interval 45 --export-on-complete"
```

- One WhatsApp bubble per pipeline phase (in-place edits within the phase).
- Do **not** default to `WHATSAPP_HOME_CHANNEL` — wrong group in multi-group setups.
- Print nothing else to WhatsApp from the agent while the streamer runs (avoid sqlite spam).

### Step 3: Check progress (when the user asks)

If the streamer is running, prefer reading its state over manual sqlite polling. Otherwise:

```bash
tail -20 /tmp/litreview-output.log
cd ~/projects/literature-review-assistant && uv run python scripts/watch_review.py --workflow-id wf-NNNN
cd ~/projects/literature-review-assistant && uv run python scripts/show_run_info.py --workflow-id wf-NNNN
```

### Step 4: On completion — Export and deliver zip

```bash
cd ~/projects/literature-review-assistant
uv run python -m src.main export --workflow-id wf-NNNN
ls runs/YYYY-MM-DD/wf-NNNN-*/run_*/submission/submission_*.zip
```
Deliver: `send_message(target='whatsapp', message='Review complete! MEDIA:/path/to/submission_*.zip')`

### Step 5: Resume (if interrupted)

```bash
uv run python -m src.main resume --workflow-id wf-NNNN
uv run python -m src.main resume --workflow-id wf-NNNN --from-phase phase_5_synthesis
```

---

## Critical constraints and pitfalls

- Use pipeline-generated writing outputs; do not draft sections manually in chat.
- Never invent citekeys; citations must come from run artifacts.
- Normalize accented surnames for citekey lookups.
- Avoid SVG-only figure pipelines for LaTeX; include PNG/PDF outputs.
- Respect scholarly API rate limits and backoffs.

### Web of Science (Clarivate) 512 errors

Clarivate WoS API has a persistent server-side 512 error that blocks the pipeline for ~35s with retries. Fix: remove `web_of_science` from `target_databases:` in `config/review.yaml` and run `--fresh`.

### Protocol generation after phase 2

After search + dedup, the pipeline calls DeepSeek (pro model) to generate the study protocol. Shows no progress for 60-90 seconds. Do not kill — wait 2-3 min. Resume if actually hung.

### Resume re-runs connectors

`resume` picks up from the last checkpoint and re-runs the connector phase (deduplicating against existing records). Remove slow/failing connectors before resuming.

### DeepSeek model split in settings.yaml

Flash (deepseek-v4-flash): bulk screening, search, adjudication. Pro (deepseek-v4-pro): extraction, quality, writing, protocol. Pro calls take 60-120s.

## Session Troubleshooting Tips

For additional edge cases discovered during live runs, see references/session-troubleshooting.md.

## Session Troubleshooting Tips

For additional edge cases discovered during live runs — WoS connector failures, API timeouts, DB-based monitoring patterns — see `references/session-troubleshooting.md`.

## Session Troubleshooting Tips

For additional edge cases discovered during live runs — WoS connector failures, API timeouts, DB-based monitoring patterns — see `references/session-troubleshooting.md`.
