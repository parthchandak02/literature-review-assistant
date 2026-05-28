#!/usr/bin/env bash
# Monitor API responsiveness while wf-0102 runs (Phase 0 E2E validation).
set -euo pipefail

RUN_ID="${1:-13f3f5b8}"
WF_ID="${2:-wf-0102}"
DB_PATH="${3:-/Users/parthchandak/projects/literature-review-assistant/runs/2026-05-27/wf-0102-what-is-the-impact-of-drone-based-medical-delivery-systems-on-ac/run_02-17-45PM/runtime.db}"
API="http://127.0.0.1:8001"
INTERVAL="${4:-90}"
MAX_ROUNDS="${5:-20}"

echo "=== Reliability monitor started $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
MONITOR_START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "run_id=$RUN_ID workflow_id=$WF_ID interval=${INTERVAL}s max_rounds=$MAX_ROUNDS monitor_start=$MONITOR_START"

health_ok=0
health_fail=0
health_slow=0

for round in $(seq 1 "$MAX_ROUNDS"); do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo ""
  echo "--- Round $round @ $ts ---"

  # Health ping (5s timeout)
  health_ms=$(curl --max-time 5 -sS -o /tmp/litreview_health.json -w '%{time_total}' "$API/api/health" 2>/dev/null || echo "timeout")
  if [[ -f /tmp/litreview_health.json ]] && grep -q '"status"' /tmp/litreview_health.json 2>/dev/null; then
    health_code="200"
  else
    health_code="000"
  fi
  if [[ "$health_code" == "200" ]]; then
    health_ok=$((health_ok + 1))
    health_ms_int=$(python3 -c "print(int(float('${health_ms:-999}')*1000))" 2>/dev/null || echo 9999)
    if (( health_ms_int > 500 )); then health_slow=$((health_slow + 1)); fi
    echo "HEALTH: OK HTTP=$health_code ${health_ms_int}ms"
  else
    health_fail=$((health_fail + 1))
    echo "HEALTH: FAIL HTTP=$health_code"
  fi

  # Concurrent reads while workflow runs
  hist_code=$(curl --max-time 8 -sS -o /dev/null -w '%{http_code}' "$API/api/history?limit=5" 2>/dev/null || echo "000")
  active_code=$(curl --max-time 8 -sS -o /dev/null -w '%{http_code}' "$API/api/history/active-run?workflow_id=$WF_ID" 2>/dev/null || echo "000")
  echo "HISTORY: HTTP=$hist_code  ACTIVE-RUN: HTTP=$active_code"

  # Latest progress from DB
  progress=$(sqlite3 "$DB_PATH" "SELECT json_extract(payload,'$.phase'), json_extract(payload,'$.current'), json_extract(payload,'$.total'), ts FROM event_log WHERE workflow_id='$WF_ID' AND event_type='progress' ORDER BY id DESC LIMIT 1;" 2>/dev/null || echo "n/a")
  echo "PROGRESS: $progress"

  latest=$(sqlite3 "$DB_PATH" "SELECT event_type, ts FROM event_log WHERE workflow_id='$WF_ID' ORDER BY id DESC LIMIT 3;" 2>/dev/null || echo "n/a")
  echo "EVENTS: $latest"

  # Terminal check (only events after monitor start)
  terminal=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM event_log WHERE workflow_id='$WF_ID' AND event_type IN ('done','error','cancelled') AND ts >= '$MONITOR_START';" 2>/dev/null || echo "0")
  if [[ "$terminal" != "0" ]]; then
    echo "TERMINAL event detected — stopping monitor"
    break
  fi

  sleep "$INTERVAL"
done

echo ""
echo "=== Summary ==="
echo "health_ok=$health_ok health_fail=$health_fail health_slow=${health_slow}ms_over_500"
