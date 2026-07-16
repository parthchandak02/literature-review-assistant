#!/usr/bin/env bash
# HTTP liveness watchdog for litreview PM2 processes.
#
# PM2 autorestart handles crash exits it observes. This script covers the gap
# where PM2 reports "online" but the process is dead or the port is unresponsive
# (zombie supervisor state). Pattern: Kubernetes liveness probe + rate-limited restart.
#
# Managed by launchd (scripts/com.parthchandak.litreview-healthwatch.plist).
# Install: ./scripts/install_pm2_watchdog.sh

set -euo pipefail

API_HEALTH_URL="${LITREVIEW_HEALTH_URL:-http://127.0.0.1:8001/api/health}"
API_PORT="${LITREVIEW_API_PORT:-8001}"
PM2_BIN="${PM2_BIN:-pm2}"

STATE_DIR="${HOME}/.cloudflared/litreview-healthwatch"
LOG_FILE="${STATE_DIR}/watchdog.log"
LOCK_DIR="${STATE_DIR}/watchdog.lock.d"
API_FAIL_FILE="${STATE_DIR}/api_failures"
TUNNEL_FAIL_FILE="${STATE_DIR}/tunnel_failures"
RESTART_LOG="${STATE_DIR}/restart_timestamps"

FAIL_THRESHOLD="${LITREVIEW_FAIL_THRESHOLD:-2}"
MAX_RESTARTS_PER_HOUR="${LITREVIEW_MAX_RESTARTS_PER_HOUR:-5}"
CURL_TIMEOUT="${LITREVIEW_CURL_TIMEOUT:-5}"

mkdir -p "${STATE_DIR}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${LOG_FILE}"
}

read_counter() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    cat "${file}"
  else
    echo 0
  fi
}

write_counter() {
  echo "$2" >"$1"
}

port_listening() {
  lsof -nP -iTCP:"${API_PORT}" -sTCP:LISTEN >/dev/null 2>&1
}

api_health_ok() {
  local body
  body="$(curl --max-time "${CURL_TIMEOUT}" -fsS "${API_HEALTH_URL}" 2>/dev/null || true)"
  [[ "${body}" == *'"status"'* ]] && [[ "${body}" == *'ok'* ]]
}

pm2_process_online() {
  local name="$1"
  local status
  status="$("${PM2_BIN}" jlist 2>/dev/null | python3 -c "
import json, sys
name = sys.argv[1]
try:
    apps = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(1)
for app in apps:
    if app.get('name') == name:
        print(app.get('pm2_env', {}).get('status', 'unknown'))
        sys.exit(0)
print('missing')
" "${name}" 2>/dev/null || echo "unknown")"
  [[ "${status}" == "online" ]]
}

pm2_has_pid() {
  local name="$1"
  local pid
  pid="$("${PM2_BIN}" pid "${name}" 2>/dev/null || true)"
  [[ -n "${pid}" && "${pid}" != "0" ]] && kill -0 "${pid}" 2>/dev/null
}

recent_restart_count() {
  local cutoff now count
  now=$(date +%s)
  cutoff=$((now - 3600))
  count=0
  if [[ -f "${RESTART_LOG}" ]]; then
    while IFS= read -r ts; do
      [[ -z "${ts}" ]] && continue
      if (( ts >= cutoff )); then
        count=$((count + 1))
      fi
    done <"${RESTART_LOG}"
  fi
  echo "${count}"
}

record_restart() {
  date +%s >>"${RESTART_LOG}"
  # Keep only last 24h of timestamps
  local cutoff
  cutoff=$(($(date +%s) - 86400))
  if [[ -f "${RESTART_LOG}" ]]; then
    awk -v c="${cutoff}" '$1 >= c' "${RESTART_LOG}" >"${RESTART_LOG}.tmp" || true
    mv "${RESTART_LOG}.tmp" "${RESTART_LOG}"
  fi
}

maybe_restart() {
  local process="$1"
  local reason="$2"
  local recent

  recent="$(recent_restart_count)"
  if (( recent >= MAX_RESTARTS_PER_HOUR )); then
    log "SKIP restart ${process}: rate limit (${recent}/${MAX_RESTARTS_PER_HOUR} in last hour). reason=${reason}"
    return 1
  fi

  log "RESTART ${process}: ${reason}"
  "${PM2_BIN}" restart "${process}" >>"${LOG_FILE}" 2>&1 || {
    log "ERROR pm2 restart ${process} failed"
    return 1
  }
  record_restart
  "${PM2_BIN}" save --force >>"${LOG_FILE}" 2>&1 || true
  return 0
}

check_api() {
  local failures healthy pid_ok port_ok

  failures="$(read_counter "${API_FAIL_FILE}")"
  healthy=false
  pid_ok=false
  port_ok=false

  if pm2_has_pid litreview-api; then
    pid_ok=true
  fi
  if port_listening; then
    port_ok=true
  fi
  if api_health_ok; then
    healthy=true
  fi

  if [[ "${healthy}" == true ]]; then
    if (( failures > 0 )); then
      log "RECOVER api: health OK after ${failures} failure(s)"
    fi
    write_counter "${API_FAIL_FILE}" 0
    return 0
  fi

  failures=$((failures + 1))
  write_counter "${API_FAIL_FILE}" "${failures}"

  local reason="health_fail failures=${failures}/${FAIL_THRESHOLD} pid_ok=${pid_ok} port_ok=${port_ok}"
  log "WARN api: ${reason}"

  if (( failures >= FAIL_THRESHOLD )); then
    maybe_restart litreview-api "${reason}"
    write_counter "${API_FAIL_FILE}" 0
  fi
}

check_tunnel() {
  local failures pid_ok online_ok

  failures="$(read_counter "${TUNNEL_FAIL_FILE}")"
  pid_ok=false
  online_ok=false

  if pm2_has_pid litreview-tunnel; then
    pid_ok=true
  fi
  if pm2_process_online litreview-tunnel; then
    online_ok=true
  fi

  if [[ "${pid_ok}" == true && "${online_ok}" == true ]]; then
    if (( failures > 0 )); then
      log "RECOVER tunnel: process OK after ${failures} failure(s)"
    fi
    write_counter "${TUNNEL_FAIL_FILE}" 0
    return 0
  fi

  failures=$((failures + 1))
  write_counter "${TUNNEL_FAIL_FILE}" "${failures}"

  local reason="process_fail failures=${failures}/${FAIL_THRESHOLD} pid_ok=${pid_ok} online_ok=${online_ok}"
  log "WARN tunnel: ${reason}"

  if (( failures >= FAIL_THRESHOLD )); then
    maybe_restart litreview-tunnel "${reason}"
    write_counter "${TUNNEL_FAIL_FILE}" 0
  fi
}

acquire_lock() {
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    exit 0
  fi
  trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT
}

main() {
  acquire_lock
  check_api
  check_tunnel
}
