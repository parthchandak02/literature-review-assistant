# Hermes monitoring and WhatsApp delivery (cron, no-agent)

Use Hermes **built-in cron** with `no_agent=True` to monitor a running review and deliver updates to the **same WhatsApp group** where the user asked. No custom streaming Python, no bridge client, no extra dependencies.

Official references: [script-only cron](https://hermes-agent.nousresearch.com/docs/guides/cron-script-only), `hermes-cron-jobs` skill, `hermes send --help`.

---

## One-time host fix (Node + gateway after `hermes update`)

If `hermes update` shows Node **v20.9.0** EBADENGINE warnings, Vite `crypto.hash` build failures, or `hermes gateway restart` exits with **launchctl 125**, run once from **Terminal.app** (logged-in Mac session):

```bash
source ~/.nvm/nvm.sh && nvm alias default 20.19.2
~/projects/literature-review-assistant/scripts/hermes-maintain.sh --update
```

After any `hermes update`, restart the gateway:

```bash
hermes gateway restart
# or
~/projects/literature-review-assistant/scripts/hermes-maintain.sh
```

---

## Preferred pattern: no-agent cron + per-workflow shell wrapper

Hermes cron `--script` must point to a file under `~/.hermes/scripts/` (bare name or absolute path). Arguments are **not** passed on the CLI — embed `workflow_id` and `chat_id` in a small wrapper Hermes writes once per run.

### 1. Wrapper template (Hermes writes `~/.hermes/scripts/litreview-watch-<wf-id>.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO="${LITREVIEW_ROOT:-$HOME/projects/literature-review-assistant}"
WF_ID="wf-NNNN"                          # set per run
CHAT_ID="120363...@g.us"                 # HERMES_SESSION_CHAT_ID from the asking group
JOB_ID=""                                # cron job id — set after create, for self-removal

cd "$REPO"

# watch_review.py: prints ONLY when phase/status changes; empty stdout = silent tick
OUTPUT="$(uv run python scripts/watch_review.py --workflow-id "$WF_ID" 2>/dev/null || true)"

if [ -z "$OUTPUT" ]; then
  exit 0
fi

echo "$OUTPUT"

# Completion: export submission zip and deliver via hermes send (no LLM)
case "$OUTPUT" in
  *status=completed*|*status=complete*|*status=done*)
  uv run python -m src.main export --workflow-id "$WF_ID"
  ZIP="$(find "$REPO/runs" -path "*${WF_ID}*/submission/submission_*.zip" 2>/dev/null | head -1)"
  if [ -n "$ZIP" ]; then
    hermes send --to "whatsapp:${CHAT_ID}" "Literature review ${WF_ID} complete. MEDIA:${ZIP}"
  else
    hermes send --to "whatsapp:${CHAT_ID}" "Literature review ${WF_ID} finished but submission zip not found — check runs/ manually."
  fi
  if [ -n "$JOB_ID" ]; then
    hermes cron remove "$JOB_ID" 2>/dev/null || true
  fi
  ;;
esac
```

```bash
chmod +x ~/.hermes/scripts/litreview-watch-wf-NNNN.sh
```

### 2. Create the cron job (from chat or CLI)

**Always set an explicit WhatsApp target** — never rely on `WHATSAPP_HOME_CHANNEL` or bare `deliver=origin` in multi-group setups.

```bash
CHAT_ID='<HERMES_SESSION_CHAT_ID from the group where the user asked>'

hermes cron create "every 10m" \
  --name "litreview-wf-NNNN" \
  --no-agent \
  --script litreview-watch-wf-NNNN.sh \
  --deliver "whatsapp:${CHAT_ID}"
```

Schedule options: `every 5m`, `every 10m`, `every 20m`, `every 1h` — user preference.

### 3. Behavior

| Tick | Result |
|------|--------|
| No state change | Empty stdout → **silent** (no WhatsApp message) |
| Phase / status change | One message with `workflow=… \| status=… \| phase=…` |
| Terminal status | Export + `hermes send` zip + remove cron job |

### 4. Lifecycle

```bash
hermes cron list
hermes cron run <job_id>      # test once
hermes cron pause <job_id>
hermes cron remove <job_id>   # manual cleanup if wrapper self-remove failed
```

---

## Chat prompt for Hermes `cronjob` tool

When the user starts a review from WhatsApp, Hermes should **automatically** (same turn, after capturing `wf-NNNN`):

1. Write `~/.hermes/scripts/litreview-watch-<wf-id>.sh` from the template above (`CHAT_ID` = `HERMES_SESSION_CHAT_ID`).
2. `cronjob(action=create, schedule="every 10m", script="litreview-watch-<wf-id>.sh", no_agent=true, deliver="whatsapp:<CHAT_ID>", name="litreview-<wf-id>")`.
3. Patch `JOB_ID` into the wrapper (or pass via `hermes cron edit` + re-write script).
4. Confirm in chat: workflow id, monitor interval, delivery group — then **stop** (do not poll manually; cron handles it).

---

## Fallback: LLM cron with script pre-check (only if export logic must reason)

If the wrapper is too brittle, use script + agent (uses tokens on every tick — avoid unless needed):

```bash
hermes cron create "every 10m" "$(< /tmp/litreview_cron_prompt.txt)" \
  --name "litreview-wf-NNNN-agent" \
  --script litreview-watch-wf-NNNN.sh \
  --deliver "whatsapp:${CHAT_ID}"
```

Prompt body (in `/tmp/litreview_cron_prompt.txt`):

> You are monitoring workflow wf-NNNN. The attached script output is the only source of truth. If empty, respond with exactly `[SILENT]`. If non-empty, summarize the change in one short WhatsApp-friendly line. If status is completed, run export and tell the user the zip path; use `hermes send` with `MEDIA:` if needed. Do not use `send_message` — cron delivery handles text.

Prefer **no-agent wrapper** above; it is zero tokens.

---

## Pitfalls

- **`deliver=origin`** pins to the chat where the cron was created — wrong group if created from CLI/SSH. Always `deliver=whatsapp:<jid>`.
- **Detached tmux** does not inherit `HERMES_SESSION_CHAT_ID` — embed `CHAT_ID` in the wrapper when writing it.
- **Cron script location** — must live under `~/.hermes/scripts/`; inline `python … --workflow-id` in `--script` is invalid.
- **Empty stdout is intentional** — `watch_review.py` deduplicates; do not spam sqlite queries from the agent while cron runs.
- **WoS 512 / protocol pause** — see main `SKILL.md` pitfalls; do not kill the pipeline during protocol generation.
