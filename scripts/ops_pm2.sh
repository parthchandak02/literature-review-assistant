#!/usr/bin/env bash
# Consolidated PM2 operations for LitReview.
#
# Usage:
#   ./scripts/ops_pm2.sh restart [flags]  # --backend --frontend --tunnel --prod-ui --all --status
#   ./scripts/ops_pm2.sh sync [--dry-run|--status]
#   ./scripts/ops_pm2.sh help
#
# Default if no subcommand: restart (backend only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT"

ECOSYSTEM_EXAMPLE="${ROOT}/ecosystem.config.example.js"
ECOSYSTEM_LIVE="${ROOT}/ecosystem.config.js"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

show_help() {
  sed -n '2,9p' "$0"
  echo
  echo "restart flags:"
  echo "  --backend    restart litreview-api"
  echo "  --frontend   restart litreview-ui (Vite dev)"
  echo "  --tunnel     restart litreview-tunnel"
  echo "  --prod-ui    pnpm build + restart litreview-api + health check"
  echo "  --all        restart api, ui, tunnel"
  echo "  --status     pm2 list only"
  echo
  echo "sync flags:"
  echo "  --dry-run    show actions only"
  echo "  --status     print kill_timeout from PM2 + configs"
}

cmd_restart() {
  local BACKEND=false
  local FRONTEND=false
  local TUNNEL=false
  local PROD_UI=false
  local ALL=false
  local STATUS_ONLY=false

  for arg in "$@"; do
    case "${arg}" in
      --backend) BACKEND=true ;;
      --frontend) FRONTEND=true ;;
      --tunnel) TUNNEL=true ;;
      --prod-ui) PROD_UI=true ;;
      --all) ALL=true ;;
      --status) STATUS_ONLY=true ;;
      -h|--help)
        show_help
        exit 0
        ;;
      *)
        echo "Unknown option: ${arg}" >&2
        exit 1
        ;;
    esac
  done

  build_frontend() {
    echo "==> frontend build"
    (
      cd frontend
      if command -v pnpm >/dev/null 2>&1 && pnpm --version >/dev/null 2>&1; then
        pnpm build
      else
        echo "pnpm unavailable; using frontend/node_modules/.bin"
        ./node_modules/.bin/tsc -b
        ./node_modules/.bin/vite build
      fi
    )
  }

  health_check() {
    require_cmd curl
    echo "==> health check"
    curl -sf http://127.0.0.1:8001/api/health
    echo
  }

  if [[ "${STATUS_ONLY}" == true ]]; then
    require_cmd pm2
    pm2 list
    exit 0
  fi

  require_cmd pm2

  if [[ "${ALL}" == true ]]; then
    BACKEND=true
    FRONTEND=true
    TUNNEL=true
  fi

  if [[ "${PROD_UI}" == true ]]; then
    build_frontend
    BACKEND=true
  fi

  if [[ "${BACKEND}" == false && "${FRONTEND}" == false && "${TUNNEL}" == false ]]; then
    BACKEND=true
  fi

  if [[ "${BACKEND}" == true ]]; then
    echo "==> pm2 restart litreview-api"
    pm2 restart litreview-api
  fi

  if [[ "${FRONTEND}" == true ]]; then
    echo "==> pm2 restart litreview-ui"
    pm2 restart litreview-ui
  fi

  if [[ "${TUNNEL}" == true ]]; then
    echo "==> pm2 restart litreview-tunnel"
    pm2 restart litreview-tunnel
  fi

  pm2 list

  if [[ "${PROD_UI}" == true ]]; then
    health_check
  fi
}

cmd_sync() {
  local DRY_RUN=false
  local STATUS_ONLY=false

  for arg in "$@"; do
    case "${arg}" in
      --dry-run) DRY_RUN=true ;;
      --status) STATUS_ONLY=true ;;
      -h|--help)
        show_help
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

  pm2_api_kill_timeout() {
    pm2 jlist 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
for p in data:
    if p.get('name') == 'litreview-api':
        print(p.get('pm2_env', {}).get('kill_timeout', ''))
        break
" 2>/dev/null || true
  }

  config_api_kill_timeout() {
    local file="$1"
    node -e "
const path = require('path');
const c = require(path.resolve(process.argv[1]));
const app = c.apps.find((a) => a.name === 'litreview-api');
if (!app) process.exit(2);
console.log(app.kill_timeout != null ? app.kill_timeout : '');
" "$file"
  }

  print_status() {
    echo "=== PM2 config kill_timeout status ==="
    echo "example (litreview-api): $(config_api_kill_timeout "${ECOSYSTEM_EXAMPLE}" 2>/dev/null || echo '?')"
    if [[ -f "${ECOSYSTEM_LIVE}" ]]; then
      echo "live file (litreview-api): $(config_api_kill_timeout "${ECOSYSTEM_LIVE}" 2>/dev/null || echo '?')"
    else
      echo "live file: missing (${ECOSYSTEM_LIVE})"
    fi
    echo "pm2 runtime (litreview-api): $(pm2_api_kill_timeout || echo '?')"
  }

  if [[ "${STATUS_ONLY}" == true ]]; then
    require_cmd node
    require_cmd pm2
    print_status
    exit 0
  fi

  require_cmd node
  require_cmd pm2

  if [[ ! -f "${ECOSYSTEM_EXAMPLE}" ]]; then
    echo "Missing ${ECOSYSTEM_EXAMPLE}" >&2
    exit 1
  fi

  local TARGET_KILL
  TARGET_KILL="$(config_api_kill_timeout "${ECOSYSTEM_EXAMPLE}")"
  if [[ -z "${TARGET_KILL}" ]]; then
    echo "Could not read litreview-api kill_timeout from example config" >&2
    exit 1
  fi

  local CREATED_LIVE=false
  if [[ ! -f "${ECOSYSTEM_LIVE}" ]]; then
    echo "Creating ${ECOSYSTEM_LIVE} from ecosystem.config.example.js"
    run cp "${ECOSYSTEM_EXAMPLE}" "${ECOSYSTEM_LIVE}"
    CREATED_LIVE=true
  fi

  local BEFORE_LIVE BEFORE_PM2 CHANGED PATCH_RESULT
  BEFORE_LIVE="$(config_api_kill_timeout "${ECOSYSTEM_LIVE}" 2>/dev/null || echo '')"
  BEFORE_PM2="$(pm2_api_kill_timeout)"

  CHANGED=false
  export ECOSYSTEM_LIVE ECOSYSTEM_EXAMPLE TARGET_KILL
  PATCH_RESULT="$(node <<'NODE'
const fs = require('fs')
const livePath = process.env.ECOSYSTEM_LIVE
const targetKill = Number(process.env.TARGET_KILL)
let text = fs.readFileSync(livePath, 'utf8')
let changed = false

const apiBlock = `// API graceful shutdown: allow in-flight HTTP and workflow teardown before SIGKILL.
const API_RESTART_POLICY = {
  ...RESTART_POLICY,
  kill_timeout: ${targetKill},
}
`

if (!text.includes('const API_RESTART_POLICY')) {
  const anchor = '}\n\nmodule.exports'
  if (!text.includes(anchor)) {
    console.log('MANUAL')
    process.exit(3)
  }
  text = text.replace(anchor, `}\n\n${apiBlock}\nmodule.exports`)
  changed = true
} else {
  const next = text.replace(
    /(const API_RESTART_POLICY = \{[\s\S]*?kill_timeout:\s*)\d+/,
    `$1${targetKill}`,
  )
  if (next !== text) {
    text = next
    changed = true
  }
}

const apiSpread = "...API_RESTART_POLICY"
if (text.includes("name: 'litreview-api'") && !text.includes(apiSpread)) {
  const litApi = /(name:\s*'litreview-api'[\s\S]*?)\.\.\.RESTART_POLICY/g
  if (litApi.test(text)) {
    text = text.replace(
      /(name:\s*'litreview-api'[\s\S]*?)\.\.\.RESTART_POLICY/,
      `$1${apiSpread}`,
    )
    changed = true
  }
}

if (changed) {
  fs.writeFileSync(livePath, text)
}
console.log(changed ? 'CHANGED' : 'OK')
NODE
)" || PATCH_RESULT="MANUAL"

  if [[ "${PATCH_RESULT}" == "MANUAL" ]]; then
    echo "Could not auto-merge API_RESTART_POLICY into ${ECOSYSTEM_LIVE}." >&2
    echo "Manual steps:" >&2
    echo "  1. Copy API_RESTART_POLICY from ecosystem.config.example.js (kill_timeout: 45000)." >&2
    echo "  2. On the litreview-api app, spread ...API_RESTART_POLICY instead of ...RESTART_POLICY." >&2
    echo "  3. pm2 startOrReload ecosystem.config.js --update-env && pm2 save --force" >&2
    echo "  4. Verify: pm2 jlist | python3 -c \"import json,sys; ...\" or pm2 show litreview-api" >&2
    exit 1
  fi

  if [[ "${PATCH_RESULT}" == "CHANGED" || "${CREATED_LIVE}" == true ]]; then
    CHANGED=true
  fi

  local AFTER_LIVE AFTER_PM2
  AFTER_LIVE="$(config_api_kill_timeout "${ECOSYSTEM_LIVE}")"

  echo "kill_timeout litreview-api:"
  echo "  example:  ${TARGET_KILL}"
  echo "  live before: ${BEFORE_LIVE:-<none>}"
  echo "  live after:  ${AFTER_LIVE}"
  echo "  pm2 before:  ${BEFORE_PM2:-<unknown>}"

  if [[ "${CHANGED}" == true ]]; then
    echo "Reloading litreview-api from ${ECOSYSTEM_LIVE}"
    run pm2 startOrReload "${ECOSYSTEM_LIVE}" --only litreview-api --update-env
    run pm2 save --force
  else
    echo "Live config already matches example kill_timeout; no PM2 reload."
  fi

  AFTER_PM2="$(pm2_api_kill_timeout)"
  echo "  pm2 after:   ${AFTER_PM2:-<unknown>}"
}

# Dispatch: default subcommand is restart (backend only).
SUBCOMMAND="restart"
ARGS=()

if [[ $# -gt 0 ]]; then
  case "$1" in
    restart|sync|help|-h|--help)
      SUBCOMMAND="$1"
      shift
      ARGS=("$@")
      ;;
    --*)
      ARGS=("$@")
      ;;
    *)
      echo "Unknown subcommand: $1" >&2
      echo "Run: ./scripts/ops_pm2.sh help" >&2
      exit 1
      ;;
  esac
fi

case "${SUBCOMMAND}" in
  restart)
    if (( ${#ARGS[@]} > 0 )); then
      cmd_restart "${ARGS[@]}"
    else
      cmd_restart
    fi
    ;;
  sync)
    if (( ${#ARGS[@]} > 0 )); then
      cmd_sync "${ARGS[@]}"
    else
      cmd_sync
    fi
    ;;
  help|-h|--help)
    show_help
    ;;
  *)
    echo "Unknown subcommand: ${SUBCOMMAND}" >&2
    exit 1
    ;;
esac
