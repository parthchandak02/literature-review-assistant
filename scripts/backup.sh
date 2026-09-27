#!/usr/bin/env bash
# Back up runs/ (every review) into Google Drive for desktop.
#
#   ./scripts/backup.sh run        # copy now (safe while reviews are running)
#   ./scripts/backup.sh install    # schedule every 6 hours via launchd
#   ./scripts/backup.sh uninstall  # remove the schedule
#   ./scripts/backup.sh status     # show destination, schedule, last run
#   ./scripts/backup.sh restore    # print how to restore from the backup
#
# The backup never deletes: runs removed locally stay in Drive.
# Override the destination with LITREVIEW_BACKUP_DIR.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/runs"
LABEL="com.litreview.runs-backup"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG="${HOME}/Library/Logs/litreview-backup.log"
INTERVAL_SECONDS=21600

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

default_dest() {
  local drive
  for drive in "${HOME}"/Library/CloudStorage/GoogleDrive-*; do
    case "${drive}" in *"("*) continue ;; esac
    if [[ -d "${drive}/My Drive" ]]; then
      printf '%s\n' "${drive}/My Drive/PROJECTS/Literature Review Assistant/runs-backup"
      return 0
    fi
  done
  return 1
}

resolve_dest() {
  if [[ -n "${LITREVIEW_BACKUP_DIR:-}" ]]; then
    printf '%s\n' "${LITREVIEW_BACKUP_DIR}"
  elif ! default_dest; then
    echo "Google Drive for desktop is not mounted under ~/Library/CloudStorage; set LITREVIEW_BACKUP_DIR." >&2
    exit 1
  fi
}

cmd_run() {
  local dest db rel target tmp count=0
  dest="$(resolve_dest)"
  [[ -d "${SRC}" ]] || { echo "No runs/ directory at ${SRC}" >&2; exit 1; }
  mkdir -p "${dest}"
  log "backup start: ${SRC} -> ${dest}"

  rsync -a \
    --exclude '*.db' --exclude '*.db-wal' --exclude '*.db-shm' --exclude '*.db-journal' \
    --exclude '.DS_Store' \
    "${SRC}/" "${dest}/"

  while IFS= read -r -d '' db; do
    rel="${db#"${SRC}/"}"
    target="${dest}/${rel}"
    mkdir -p "$(dirname "${target}")"
    tmp="${target}.partial"
    if sqlite3 "${db}" ".timeout 10000" ".backup '${tmp//\'/\'\'}'"; then
      mv -f "${tmp}" "${target}"
      count=$((count + 1))
    else
      rm -f "${tmp}"
      log "WARN: could not snapshot ${rel}"
    fi
  done < <(find "${SRC}" -type f -name '*.db' -print0)

  date '+%Y-%m-%d %H:%M:%S' > "${dest}/.last_backup"
  log "backup done: ${count} database(s) snapshotted"
}

cmd_install() {
  local dest
  dest="$(resolve_dest)"
  mkdir -p "$(dirname "${PLIST}")" "$(dirname "${LOG}")"
  cat > "${PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${REPO_ROOT}/scripts/backup.sh</string>
    <string>run</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>LITREVIEW_BACKUP_DIR</key><string>${dest}</string></dict>
  <key>StartInterval</key><integer>${INTERVAL_SECONDS}</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>${LOG}</string>
  <key>StandardErrorPath</key><string>${LOG}</string>
</dict>
</plist>
PLIST
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "${PLIST}"
  echo "Scheduled every $((INTERVAL_SECONDS / 3600))h -> ${dest}"
  echo "Log: ${LOG}"
}

cmd_uninstall() {
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  rm -f "${PLIST}"
  echo "Schedule removed (backup files in Drive are kept)."
}

cmd_status() {
  local dest
  dest="$(resolve_dest)"
  echo "Source:      ${SRC}"
  echo "Destination: ${dest}"
  if [[ -f "${dest}/.last_backup" ]]; then echo "Last backup: $(cat "${dest}/.last_backup")"; else echo "Last backup: never"; fi
  if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then echo "Schedule:    installed (every $((INTERVAL_SECONDS / 3600))h)"; else echo "Schedule:    not installed"; fi
  [[ -f "${LOG}" ]] && { echo "Recent log:"; tail -n 3 "${LOG}"; }
}

cmd_restore() {
  local dest
  dest="$(resolve_dest)"
  cat <<EOF
Restore reviews from the Drive backup (stop the API first so no run is writing):
  ./scripts/ops_pm2.sh restart --backend-only   # after the copy below
  rsync -a --ignore-existing "${dest}/" "${SRC}/"
--ignore-existing only adds missing runs; it never overwrites local files.
EOF
}

case "${1:-help}" in
  run) cmd_run ;;
  install) cmd_install ;;
  uninstall) cmd_uninstall ;;
  status) cmd_status ;;
  restore) cmd_restore ;;
  help | -h | --help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "Unknown command: $1" >&2; sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
esac
