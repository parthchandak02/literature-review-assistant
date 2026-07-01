# Hermes no-agent monitoring templates

## One-time host fix (Node + gateway after `hermes update`)

If `hermes update` shows Node **v20.9.0** EBADENGINE warnings, Vite `crypto.hash` build failures, or `hermes gateway restart` exits with **launchctl 125**, run once from **Terminal.app** (logged-in Mac session):

```bash
# 1) Pin nvm default (beats stale /usr/local/bin/node v20.9)
source ~/.nvm/nvm.sh && nvm alias default 20.19.2

# 2) Optional but recommended: repoint system node symlinks
sudo ln -sf ~/.nvm/versions/node/v20.19.2/bin/node /usr/local/bin/node
sudo ln -sf ~/.nvm/versions/node/v20.19.2/bin/npm /usr/local/bin/npm

# 3) Post-update maintenance from this repo
~/projects/literature-review-assistant/scripts/hermes-maintain.sh --update
```

`~/.zprofile` loads nvm 20.19+ for login shells so plain `hermes update` uses the right Node afterward.

After any `hermes update`, restart with either:

```bash
hermes gateway restart    # uses launchd, or detached fallback on error 125
# or
~/projects/literature-review-assistant/scripts/hermes-maintain.sh
```

---

Use these patterns to monitor long reviews without consuming Hermes model turns.

## Why no-agent mode

- `no_agent=True` runs the script directly on schedule.
- Empty stdout produces a silent tick.
- Non-empty stdout is delivered as-is.
- Non-zero exit emits an error alert.

This is the safest setup when your Hermes profile has a tight iteration budget.

## Preferred: WhatsApp streamer (in-place phase updates)

For one-off reviews started from a WhatsApp group, launch the bridge streamer with that group's JID (not `WHATSAPP_HOME_CHANNEL`):

```bash
CHAT_ID='<HERMES_SESSION_CHAT_ID from the group where the user asked>'
"$LITREVIEW_ROOT/scripts/stream_review_whatsapp.py" \
  --workflow-id wf-XXXX --chat-id "$CHAT_ID" --interval 45 --export-on-complete
```

Requires `hermes gateway` running. Script prints nothing to stdout (avoids duplicate cron delivery).

## Fallback: one-shot watcher (new message on change only)

```bash
python "$LITREVIEW_ROOT/scripts/watch_review.py" --workflow-id wf-XXXX
```

## Chat prompt template (Hermes cronjob tool)

> Every 10 minutes, run `python "$LITREVIEW_ROOT/scripts/watch_review.py" --workflow-id wf-XXXX`. If output is empty, stay silent. If output is non-empty, deliver it. Use no-agent mode.

## CLI examples

```bash
# Create no-agent cron job
hermes cron create \
  --name litreview-wf-XXXX \
  --schedule "every 10m" \
  --script "python \"$LITREVIEW_ROOT/scripts/watch_review.py\" --workflow-id wf-XXXX" \
  --no-agent

# List jobs
hermes cron list

# Force one run now
hermes cron run litreview-wf-XXXX
```

## Optional follow mode (interactive only)

```bash
python "$LITREVIEW_ROOT/scripts/watch_review.py" --workflow-id wf-XXXX --follow
```

Follow mode is for active terminal sessions, not cron.
