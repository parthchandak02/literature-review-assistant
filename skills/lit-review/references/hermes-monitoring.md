# Hermes no-agent monitoring templates

Use these patterns to monitor long reviews without consuming Hermes model turns.

## Why no-agent mode

- `no_agent=True` runs the script directly on schedule.
- Empty stdout produces a silent tick.
- Non-empty stdout is delivered as-is.
- Non-zero exit emits an error alert.

This is the safest setup when your Hermes profile has a tight iteration budget.

## Recommended watcher command

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
