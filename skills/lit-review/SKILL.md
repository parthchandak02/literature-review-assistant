---
name: lit-review
description: "Run systematic literature reviews end-to-end from WhatsApp or chat: generate config, start pipeline, cron-monitor with watch_review.py, deliver submission zip on completion."
version: 1.8.0
author: Hermes Agent
platforms: [macos, linux]
metadata:
  hermes:
    tags: [literature-review, systematic-review, PRISMA, research, commands, LaTeX, whatsapp, cron]
---

# Systematic Literature Review Pipeline (lit-review)

High-precision operator playbook for `literature-review-assistant`. When a user says **`/lit-review "some topic"`**, **`/skill lit-review`**, or asks for a systematic review on a topic in WhatsApp, follow this skill end-to-end: **start → cron-monitor → deliver zip** — with minimal Hermes token use after kickoff.

---

## WhatsApp / chat trigger (do this when invoked)

**Input examples:** `/lit-review "GLP-1 and cardiovascular outcomes"`, "run a lit review on …", "systematic review: …"

**Required context:** `HERMES_SESSION_CHAT_ID` = JID of the group (or DM) where the user asked. Use it for cron `deliver` and `hermes send`. Do **not** default to `WHATSAPP_HOME_CHANNEL`.

### Automatic playbook (one kickoff turn + cron; no manual polling)

| Step | Action |
|------|--------|
| 1 | `cd ~/projects/literature-review-assistant` |
| 2 | `uv run python scripts/start_review.py --question "<topic>"` → review `config/review.yaml` |
| 3 | Launch pipeline in detached tmux; capture **workflow id** (`wf-NNNN`) from startup log |
| 4 | Write `~/.hermes/scripts/litreview-watch-wf-NNNN.sh` (template in `references/hermes-monitoring.md`) with `CHAT_ID` + `WF_ID` |
| 5 | Create **no-agent** cron: `every 10m` (or user-requested 5m / 20m / 60m), `--script litreview-watch-wf-NNNN.sh`, `--deliver whatsapp:<CHAT_ID>` |
| 6 | Reply once in chat: started `wf-NNNN`, monitoring every N minutes, zip will arrive here when done |
| 7 | **Stop** — do not poll sqlite or re-run `watch_review.py` manually; cron owns monitoring |

On completion the wrapper exports (`src.main export`) and runs `hermes send … MEDIA:…zip`, then removes the cron job.

**Related skills:** `hermes-cron-jobs` (no_agent, `[SILENT]`, delivery targets), `hermes-agent` (`/goal` for standing work if user prefers that over cron).

---

## Repo location (this machine)

**REPO_ROOT:** `~/projects/literature-review-assistant/` (`LITREVIEW_ROOT`)

Already cloned, `uv sync`'d, credentials in repo `.env`. Models in `config/settings.yaml`.

### One-time setup on a fresh machine

1. `git clone https://github.com/parthchandak02/literature-review-assistant.git`
2. `cd literature-review-assistant && uv sync`
3. Copy example `.env` and fill API keys
4. `uv run python -m src.main --help`
5. Hermes host: `nvm alias default 20.19.2`, run `scripts/hermes-maintain.sh` once (see `references/hermes-monitoring.md`)

---

## Key paths

| Path | Role |
|------|------|
| `scripts/start_review.py` | Question → `config/review.yaml` |
| `src/main.py` | `run`, `resume`, `export`, `validate` |
| `scripts/watch_review.py` | Low-noise monitor (stdout only on state change) — used by cron wrapper |
| `scripts/show_run_info.py` | One-shot metadata for a workflow id |
| `config/review.yaml` | Active review config (overwritten each `start_review.py`) |
| `runs/workflows_registry.db` | workflow id → runtime db path |
| `references/hermes-monitoring.md` | Cron wrapper template, `hermes send`, pitfalls |

---

## Low-cost operating contract

- **Kickoff (one agent turn):** config + tmux start + cron create + short confirmation.
- **After kickoff:** cron `no_agent` monitors — **zero LLM tokens** per tick.
- **Do not** manually poll progress while cron is active.
- **Do not** patch `runs/` artifacts.
- **Resume** replays use `config_snapshot.yaml` in the run directory (`run --config … --fresh` or `resume --workflow-id`).

---

## Pipeline phases (typical 20–60 min)

| Phase | What happens | Est. time |
|-------|-------------|-----------|
| Start | Load config, init DB, register workflow id | ~30s |
| Search | Connectors, dedup, protocol | 2–5 min |
| Screening | Dual LLM screening | 10–20 min |
| Extraction | Extraction + RoB / GRADE | 5–15 min |
| Synthesis | Meta-analysis or narrative | 5–10 min |
| Writing | Sections + manuscript assembly | 5–10 min |
| Finalize | References, BibTeX, LaTeX | ~1 min |

---

## Step-by-step commands (reference)

### Step 1 — Generate config

```bash
cd ~/projects/literature-review-assistant
uv run python scripts/start_review.py --question "YOUR RESEARCH QUESTION"
```

Optional: `--profile standard` (default) or `health_sdg`. Skim `pico`, `keywords`, `inclusion_criteria`, `search_overrides`.

### Step 2 — Launch in tmux

```bash
tmux new-session -d -s "litreview-wf-NNNN" \
  'cd ~/projects/literature-review-assistant && uv run python -m src.main run --config config/review.yaml 2>&1 | tee /tmp/litreview-wf-NNNN.log; sleep 9999'
```

Capture **workflow id** from log (e.g. `wf-0105`).

### Step 2b — Monitor + deliver (Hermes cron; required for WhatsApp runs)

See **`references/hermes-monitoring.md`** for the wrapper script and:

```bash
hermes cron create "every 10m" \
  --name "litreview-wf-NNNN" \
  --no-agent \
  --script litreview-watch-wf-NNNN.sh \
  --deliver "whatsapp:<HERMES_SESSION_CHAT_ID>"
```

### Step 3 — Manual progress check (only if cron is not running)

```bash
uv run python scripts/watch_review.py --workflow-id wf-NNNN
uv run python scripts/show_run_info.py --workflow-id wf-NNNN
tail -30 /tmp/litreview-wf-NNNN.log
```

### Step 4 — Export and deliver (manual fallback)

If cron wrapper did not run export:

```bash
uv run python -m src.main export --workflow-id wf-NNNN
hermes send --to "whatsapp:<CHAT_ID>" "Complete. MEDIA:/path/to/submission_*.zip"
```

### Step 5 — Resume (if interrupted)

```bash
uv run python -m src.main resume --workflow-id wf-NNNN
# or from phase:
uv run python -m src.main resume --workflow-id wf-NNNN --from-phase phase_5_synthesis
```

Re-create or resume the cron job for the same workflow id if monitoring should continue.

---

## Critical constraints and pitfalls

- Use pipeline-generated writing; do not draft manuscript sections in chat.
- Never invent citekeys; citations must come from run artifacts.
- **Web of Science 512:** remove `web_of_science` from `target_databases` in `config/review.yaml` and `--fresh` if blocked.
- **Protocol generation** after search can idle 60–90s (DeepSeek pro) — do not kill; wait 2–3 min.
- **Resume re-runs connectors** — remove slow/failing connectors before resume.
- **DeepSeek split:** flash = screening/search; pro = extraction/writing/protocol (60–120s per call).

More edge cases: `references/session-troubleshooting.md`.
