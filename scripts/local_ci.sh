#!/usr/bin/env bash
# Local CI parity with planned GitHub Actions jobs (Phase 0.1).
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

echo "==> replay fixture schema"
uv run python scripts/check_replay_fixture_schema.py

FIXTURE_DIR="$ROOT/tests/fixtures/replay"
REPLAY_WORKFLOW_ID="$(uv run python -c 'import json, pathlib; m=json.loads(pathlib.Path("tests/fixtures/replay/manifest.json").read_text()); print(m["workflow_id"])')"
REPLAY_DB_PATH="$FIXTURE_DIR/runtime.db"

export WORKFLOW_REPLAY_ID="$REPLAY_WORKFLOW_ID"
export WORKFLOW_REPLAY_DB_PATH="$REPLAY_DB_PATH"

echo "==> validate_workflow_replay (profile=local, fixture)"
uv run python scripts/validate_workflow_replay.py \
  --workflow-id "$REPLAY_WORKFLOW_ID" \
  --db-path "$REPLAY_DB_PATH" \
  --profile local \
  --fail-on-error

echo "local CI passed"
