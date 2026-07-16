#!/usr/bin/env bash
# Production deploy: build frontend static assets, restart API, verify health.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

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

echo "==> pm2 restart litreview-api"
pm2 restart litreview-api

echo "==> health check"
curl -sf http://127.0.0.1:8001/api/health
echo
