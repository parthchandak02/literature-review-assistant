#!/usr/bin/env bash
# LitReview script index — plain-language routing for humans and agents.
# Canonical detail: docs/SCRIPTS.md
set -euo pipefail

cat <<'EOF'
LitReview scripts — what to run when

  Full reference: docs/SCRIPTS.md
  Per-script help: <script> --help  or  ./scripts/ops_pm2.sh help

WHEN YOU NEED TO...                          COMMAND
---------------------------------------------------------------------------
Restart local dev (api + ui)                  make pm2-restart
                                             ./scripts/ops_pm2.sh restart
Restart API only                             ./scripts/ops_pm2.sh restart --backend-only
Restart Vite dev only (5173)                 ./scripts/ops_pm2.sh restart --frontend-only

Ship frontend to production URL              make deploy-prod
                                             ./scripts/ops_pm2.sh restart --prod-ui

Run all tests before commit                  make check-local
Full pre-release gate                        make check-release

Check API docs match routes (one check)      make check-api
                                             uv run python scripts/check.py api

Validate replay test fixture                 uv run python scripts/check.py replay-fixture

Validate a workflow replay DB                uv run python scripts/check.py replay-workflow \\
                                               --workflow-id wf-XXXX --profile local --fail-on-error

Start config from a research question        uv run python scripts/review.py start \\
                                               --question "your question"

Monitor workflow stage (cron-friendly)       uv run python scripts/review.py watch \\
                                               --workflow-id wf-XXXX

Show run diagnostics                         uv run python scripts/review.py info \\
                                               --workflow-id wf-XXXX

Fix manuscript sections on an old run        uv run python scripts/repair.py finalize \\
                                               --run-dir runs/<run_id>

Re-run failed extraction                     uv run python scripts/repair.py re-extract \\
                                               --run-dir runs/<run_id>

Patch missing citations                      uv run python scripts/repair.py inject-citations \\
                                               --workflow-id wf-XXXX

Rebuild replay test fixture after schema     uv run python scripts/repair.py regen-replay-fixture \\
                                               --workflow-id wf-XXXX

Hermes operator setup                        ./scripts/hermes.sh maintain

ENTRYPOINTS (user-facing — use these)
  scripts/ops_pm2.sh   servers (PM2 restart, deploy)
  scripts/check.sh     run full test suites (local | release)
  scripts/check.py     individual quality checks (api | replay-fixture | replay-workflow)
  scripts/review.py    start | watch | info
  scripts/repair.py    fix old runs (finalize, re-extract, inject-citations, regen-replay-fixture)
  scripts/hermes.sh    Hermes maintain | link-skill

DO NOT call scripts/lib/* directly — implementation modules only.

Makefile aliases (old names still work): local-ci, release-check, parity
EOF
