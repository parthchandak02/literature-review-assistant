#!/usr/bin/env bash
# Sprint A release gate: local_ci parity plus build, lifecycle integration, and isolated replay DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> ruff check"
uv run ruff check .

echo "==> pytest tests/unit"
uv run pytest tests/unit -q

echo "==> pytest integration smoke (API endpoint parity gate)"
uv run pytest tests/integration/test_api_endpoint_parity_gate.py -q

echo "==> scripts/check_spec_endpoint_parity.py"
uv run python scripts/check_spec_endpoint_parity.py

echo "==> frontend lint / typecheck / test"
(
  cd frontend
  if command -v pnpm >/dev/null 2>&1 && pnpm --version >/dev/null 2>&1; then
    pnpm lint
    pnpm typecheck
    pnpm test
  else
    echo "pnpm unavailable; using frontend/node_modules/.bin"
    ./node_modules/.bin/eslint .
    ./node_modules/.bin/tsc -b --noEmit
    ./node_modules/.bin/vitest run
  fi
)

echo "==> frontend production build"
(
  cd frontend
  if command -v pnpm >/dev/null 2>&1 && pnpm --version >/dev/null 2>&1; then
    pnpm build
  else
    echo "pnpm unavailable; using frontend/node_modules/.bin"
    ./node_modules/.bin/vite build
  fi
)

echo "==> integration: lifecycle restart"
uv run pytest tests/integration/test_lifecycle_restart.py -q

echo "==> integration: app shutdown"
uv run pytest tests/integration/test_app_shutdown.py -q

echo "==> unit: event store durability"
uv run pytest tests/unit/test_event_store_durability.py -q

echo "==> integration: API endpoints (full parity file)"
uv run pytest tests/integration/test_api_endpoints.py -q

echo "==> integration: resume workflow smoke (mocked LLM)"
uv run pytest tests/integration/test_resume_workflow_smoke.py -q

echo "==> integration: resume rewind"
uv run pytest tests/integration/test_resume_rewind.py -q

echo "==> integration: graph transitions"
uv run pytest tests/integration/test_graph_transitions.py -q

echo "==> integration: golden path API"
uv run pytest tests/integration/test_golden_path_api.py -q

echo "==> replay fixture schema"
uv run python scripts/check_replay_fixture_schema.py

FIXTURE_DIR="$ROOT/tests/fixtures/replay"
MANIFEST_PATH="$FIXTURE_DIR/manifest.json"

_replay_profile_count() {
  uv run python -c '
import json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
profiles = manifest.get("profiles")
if isinstance(profiles, dict) and profiles:
    print(len(profiles))
else:
    print(1)
' "$MANIFEST_PATH"
}

PROFILE_COUNT="$(_replay_profile_count)"
PROFILE_INDEX=0
while [ "$PROFILE_INDEX" -lt "$PROFILE_COUNT" ]; do
  {
    read -r REPLAY_PROFILE_NAME
    read -r REPLAY_WORKFLOW_ID
    read -r REPLAY_DB_NAME
    read -r REPLAY_VALIDATE_PROFILE
  } <<EOF
$(uv run python -c '
import json, pathlib, sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
index = int(sys.argv[2])
profiles = manifest.get("profiles")
entries = []
if isinstance(profiles, dict) and profiles:
    for name, payload in profiles.items():
        if isinstance(payload, dict):
            entries.append((name, payload))
else:
    entries = [("default", {"workflow_id": manifest.get("workflow_id"), "files": manifest.get("files", {})})]
name, payload = entries[index]
files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
runtime_db = files.get("runtime_db", "runtime.db")
workflow_id = payload.get("workflow_id", manifest.get("workflow_id", ""))
validate_profile = "adversarial" if name == "adversarial" else "local"
print(name)
print(workflow_id)
print(runtime_db)
print(validate_profile)
' "$MANIFEST_PATH" "$PROFILE_INDEX")
EOF

  REPLAY_TMP="$(mktemp -d "${TMPDIR:-/tmp}/litreview-replay.XXXXXX")"
  cleanup_replay_tmp() {
    rm -rf "$REPLAY_TMP"
  }
  trap cleanup_replay_tmp EXIT

  cp "$FIXTURE_DIR/$REPLAY_DB_NAME" "$REPLAY_TMP/runtime.db"
  REPLAY_DB_PATH="$REPLAY_TMP/runtime.db"

  export WORKFLOW_REPLAY_ID="$REPLAY_WORKFLOW_ID"
  export WORKFLOW_REPLAY_DB_PATH="$REPLAY_DB_PATH"

  echo "==> validate_workflow_replay (profile=$REPLAY_VALIDATE_PROFILE, manifest=$REPLAY_PROFILE_NAME, workflow=$REPLAY_WORKFLOW_ID, db=$REPLAY_DB_NAME)"
  uv run python scripts/validate_workflow_replay.py \
    --workflow-id "$REPLAY_WORKFLOW_ID" \
    --db-path "$REPLAY_DB_PATH" \
    --profile "$REPLAY_VALIDATE_PROFILE" \
    --fail-on-error

  PROFILE_INDEX=$((PROFILE_INDEX + 1))
  trap - EXIT
  cleanup_replay_tmp
done

echo "release check passed"
