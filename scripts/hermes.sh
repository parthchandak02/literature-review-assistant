#!/usr/bin/env bash
# Hermes operator helpers for literature-review-assistant.
#
# Usage:
#   ./scripts/hermes.sh maintain [--update]
#   ./scripts/hermes.sh link-skill
#   ./scripts/hermes.sh help

set -euo pipefail

print_stale_pipeline_warning() {
  cat <<'EOF' >&2
WARNING: Hermes lit-review flow may not reflect recent pipeline changes (PROSPERO gate, config-draft API, screening review UI, phase order). Verify against docs/ARCHITECTURE.md before starting new runs via Hermes. Prefer web UI or uv run python -m src.main for production runs.
EOF
}

log() { printf '→ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }

HERMES_AGENT="${HERMES_AGENT:-$HOME/.hermes/hermes-agent}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
NODE_TARGET="${NODE_TARGET:-20.19.2}"

ensure_nvm_node() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
    warn "nvm not found at $NVM_DIR — install Node ${NODE_TARGET}+ manually"
    return 1
  fi
  # shellcheck source=/dev/null
  . "$NVM_DIR/nvm.sh"
  if ! nvm ls "$NODE_TARGET" &>/dev/null; then
    log "Installing Node ${NODE_TARGET} via nvm..."
    nvm install "$NODE_TARGET"
  fi
  nvm alias default "$NODE_TARGET" >/dev/null
  nvm use "$NODE_TARGET" >/dev/null
  export PATH="$NVM_DIR/versions/node/v${NODE_TARGET}/bin:$PATH"
  log "Node $(node -v) active (nvm default ${NODE_TARGET})"
}

warn_stale_system_node() {
  local stale="/usr/local/bin/node"
  if [[ -x "$stale" ]]; then
    local ver
    ver="$("$stale" -v 2>/dev/null || true)"
    if [[ "$ver" == v20.9.* ]] || [[ "$ver" < v20.19.0 ]]; then
      warn "Stale Node at $stale ($ver) shadows nvm in non-login shells."
      warn "One-time fix (recommended): sudo ln -sf \"$NVM_DIR/versions/node/v${NODE_TARGET}/bin/node\" \"$stale\""
      warn "  and: sudo ln -sf \"$NVM_DIR/versions/node/v${NODE_TARGET}/bin/npm\" /usr/local/bin/npm"
    fi
  fi
}

fix_agent_browser_audit() {
  local dir="$HERMES_AGENT"
  if [[ ! -f "$dir/package.json" ]]; then
    return 0
  fi
  log "Refreshing Hermes npm deps (repo root)..."
  (cd "$dir" && npm install --no-fund --no-audit)
  if [[ -d "$dir/node_modules/agent-browser" ]]; then
    log "npm audit fix (agent-browser)..."
    (cd "$dir" && npm audit fix --omit=dev 2>/dev/null) || warn "npm audit fix had warnings (non-fatal)"
  fi
}

build_hermes_web() {
  if [[ ! -d "$HERMES_AGENT/web" ]]; then
    return 0
  fi
  log "Building Hermes web UI..."
  if (cd "$HERMES_AGENT/web" && npm run build --no-fund --no-audit); then
    log "Web UI build OK"
  else
    warn "Web UI build failed — check Node >= 20.19 (node -v)"
  fi
}

gateway_start_with_fallback() {
  if ! command -v hermes &>/dev/null; then
    warn "hermes not on PATH"
    return 1
  fi
  log "Starting Hermes gateway..."
  if hermes gateway start 2>/dev/null; then
    log "Gateway started via launchd"
    return 0
  fi
  warn "launchd start failed — starting detached gateway (same as Hermes fallback)"
  py="$(command -v python3)"
  nohup "$py" -m hermes_cli.main gateway run --replace \
    >>"$HERMES_HOME/logs/gateway.log" 2>>"$HERMES_HOME/logs/gateway.error.log" &
  sleep 2
  if pgrep -f "hermes_cli.main gateway run" >/dev/null 2>&1; then
    log "Gateway running in background (detached). Logs: $HERMES_HOME/logs/gateway.log"
    return 0
  fi
  warn "Gateway may not have started — check $HERMES_HOME/logs/gateway.error.log"
  return 1
}

cmd_link_skill() {
  local repo_root
  if [[ -n "${LITREVIEW_ROOT:-}" ]]; then
    repo_root="${LITREVIEW_ROOT}"
  else
    repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  fi

  local skill_source="${repo_root}/skills/lit-review"
  local skill_target="${HOME}/.hermes/skills/research/lit-review"

  if [[ ! -d "${skill_source}" ]]; then
    echo "Error: canonical skill not found at ${skill_source}" >&2
    exit 1
  fi

  mkdir -p "${HOME}/.hermes/skills/research"
  ln -sfn "${skill_source}" "${skill_target}"

  echo "Linked Hermes skill:"
  echo "  ${skill_target} -> ${skill_source}"
  echo "Verify with:"
  echo "  ls -la \"${skill_target}\""
}

cmd_maintain() {
  local do_update=false
  for arg in "$@"; do
    case "$arg" in
      --update) do_update=true ;;
      -h|--help)
        echo "Usage: ./scripts/hermes.sh maintain [--update]"
        exit 0
        ;;
      *)
        echo "Unknown option: $arg" >&2
        exit 1
        ;;
    esac
  done

  ensure_nvm_node
  warn_stale_system_node

  if $do_update; then
    log "Running hermes update (with nvm Node on PATH)..."
    hermes update
  fi

  fix_agent_browser_audit
  build_hermes_web
  gateway_start_with_fallback
  cmd_link_skill

  log "Done. Verify: hermes gateway status && hermes doctor"
}

show_help() {
  sed -n '2,7p' "$0"
  echo
  echo "Subcommands:"
  echo "  maintain [--update]   Post-update Hermes maintenance (Node, gateway, skill link)"
  echo "  link-skill            Symlink skills/lit-review into ~/.hermes/skills/research/"
}

print_stale_pipeline_warning

SUBCOMMAND="${1:-}"
shift || true

case "${SUBCOMMAND}" in
  maintain)
    cmd_maintain "$@"
    ;;
  link-skill)
    cmd_link_skill "$@"
    ;;
  help|-h|--help|"")
    show_help
    ;;
  *)
    echo "Unknown subcommand: ${SUBCOMMAND}" >&2
    show_help >&2
    exit 1
    ;;
esac
