#!/usr/bin/env bash
# Install PM2 hardening: ecosystem restart policy + HTTP liveness watchdog (launchd).
#
# Usage:
#   ./scripts/install_pm2_watchdog.sh           # install watchdog + reload PM2 apps
#   ./scripts/install_pm2_watchdog.sh --dry-run # print actions only
#   ./scripts/install_pm2_watchdog.sh --status  # show watchdog + health state

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ECOSYSTEM_EXAMPLE="${PROJECT_DIR}/ecosystem.config.example.js"
ECOSYSTEM_LIVE="${PROJECT_DIR}/ecosystem.config.js"
WATCHDOG_SOURCE="${SCRIPT_DIR}/pm2_health_watchdog.sh"
WATCHDOG_INSTALLED="${HOME}/.cloudflared/bin/pm2_health_watchdog.sh"
PLIST_TEMPLATE="${SCRIPT_DIR}/com.parthchandak.litreview-healthwatch.plist"
PLIST_DEST="${HOME}/Library/LaunchAgents/com.parthchandak.litreview-healthwatch.plist"
STATE_DIR="${HOME}/.cloudflared/litreview-healthwatch"
DRY_RUN=false
STATUS_ONLY=false

for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    --status) STATUS_ONLY=true ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: ${arg}" >&2
      exit 1
      ;;
  esac
done

run() {
  if [[ "${DRY_RUN}" == true ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

print_status() {
  echo "=== LitReview PM2 watchdog status ==="
  echo "project: ${PROJECT_DIR}"
  echo "watchdog log: ${STATE_DIR}/watchdog.log"
  echo ""
  echo "launchd:"
  launchctl print "gui/$(id -u)/com.parthchandak.litreview-healthwatch" 2>/dev/null | head -20 || echo "  not loaded"
  echo ""
  echo "pm2:"
  pm2 list
  echo ""
  echo "api health:"
  curl --max-time 5 -fsS "http://127.0.0.1:8001/api/health" 2>/dev/null || echo "  FAIL"
  echo ""
  if [[ -f "${STATE_DIR}/watchdog.log" ]]; then
    echo "recent watchdog events:"
    tail -10 "${STATE_DIR}/watchdog.log"
  fi
}

if [[ "${STATUS_ONLY}" == true ]]; then
  print_status
  exit 0
fi

require_cmd pm2
require_cmd python3
require_cmd lsof
require_cmd curl
require_cmd launchctl

if [[ ! -f "${ECOSYSTEM_EXAMPLE}" ]]; then
  echo "Missing ${ECOSYSTEM_EXAMPLE}" >&2
  exit 1
fi

run chmod +x "${WATCHDOG_SOURCE}"
run mkdir -p "${HOME}/.cloudflared/bin"
run cp "${WATCHDOG_SOURCE}" "${WATCHDOG_INSTALLED}"
run chmod +x "${WATCHDOG_INSTALLED}"

# Keep live ecosystem in sync with hardened template.
if [[ ! -f "${ECOSYSTEM_LIVE}" ]] || ! cmp -s "${ECOSYSTEM_EXAMPLE}" "${ECOSYSTEM_LIVE}"; then
  echo "Updating ${ECOSYSTEM_LIVE} from ecosystem.config.example.js"
  run cp "${ECOSYSTEM_EXAMPLE}" "${ECOSYSTEM_LIVE}"
fi

PM2_BIN="$(command -v pm2)"
PM2_BIN_DIR="$(dirname "${PM2_BIN}")"
LAUNCHD_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PM2_BIN_DIR}:${HOME}/bin"
run mkdir -p "${STATE_DIR}" "${HOME}/Library/LaunchAgents"

TMP_PLIST="$(mktemp)"
sed \
  -e "s|@@WATCHDOG_SCRIPT@@|${WATCHDOG_INSTALLED}|g" \
  -e "s|@@STATE_DIR@@|${STATE_DIR}|g" \
  -e "s|@@PM2_BIN@@|${PM2_BIN}|g" \
  -e "s|@@LAUNCHD_PATH@@|${LAUNCHD_PATH}|g" \
  "${PLIST_TEMPLATE}" >"${TMP_PLIST}"
run cp "${TMP_PLIST}" "${PLIST_DEST}"
rm -f "${TMP_PLIST}"

LABEL="com.parthchandak.litreview-healthwatch"
run launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
run launchctl bootstrap "gui/$(id -u)" "${PLIST_DEST}"
run launchctl enable "gui/$(id -u)/${LABEL}" 2>/dev/null || true

echo "Reloading PM2 apps from ecosystem.config.js"
run pm2 startOrReload "${ECOSYSTEM_LIVE}" --update-env
run pm2 save --force

echo ""
echo "Installed."
echo "  Watchdog runs every 60s via launchd (${LABEL})"
echo "  Logs: ${STATE_DIR}/watchdog.log"
echo "  Status: ./scripts/install_pm2_watchdog.sh --status"
echo "  Manual probe: ${WATCHDOG_INSTALLED}"
echo ""
echo "Boot persistence: ensure PM2 resurrect launch agent is loaded (com.cloudflare.litreview)."
echo "Optional one-time setup: pm2 startup launchd -u $(whoami) --hp ${HOME}"

if [[ "${DRY_RUN}" == false ]]; then
  "${WATCHDOG_INSTALLED}" || true
  print_status
fi
