---
name: restart
description: Restart local PM2 services (backend, frontend, tunnel, or production UI). Use when the user asks to restart services, reload after src/ or frontend changes, or invokes /restart.
disable-model-invocation: true
---

# Restart

Canonical PM2 restart workflow for local development. Always use `./scripts/ops_pm2.sh`; do not improvise raw `pm2` commands unless the script fails.

Process names (exact): `litreview-api`, `litreview-ui`, `litreview-tunnel`.

## Intent routing

| User intent | Command |
|-------------|---------|
| `/restart` or local dev reload after code changes | `./scripts/ops_pm2.sh restart` |
| Backend only (fast path after `src/` changes) | `./scripts/ops_pm2.sh restart --backend-only` |
| Vite dev server only (port 5173) | `./scripts/ops_pm2.sh restart --frontend-only` |
| Tunnel only (cloudflared config changes) | `./scripts/ops_pm2.sh restart --tunnel-only` |
| All PM2 apps (api, ui, tunnel) | `./scripts/ops_pm2.sh restart --all` |
| Production URL (build `frontend/dist`, API serves on 8001) | `./scripts/ops_pm2.sh restart --prod-ui` or `make deploy-prod` |
| Status only | `./scripts/ops_pm2.sh restart --status` |

Makefile aliases: `make pm2-restart` (api + ui), `make deploy-prod` (prod UI).

## Sequence

1. Infer scope from user message (default: backend + frontend).
2. Run the matching command from the table above from repo root.
3. Confirm `pm2 list` shows required processes online.
4. For `--prod-ui`, verify `curl -sf http://127.0.0.1:8001/api/health` succeeds (script runs this automatically).

## Manual fallback (script broken only)

```bash
pm2 restart litreview-api      # backend (port 8001)
pm2 restart litreview-ui        # Vite dev (port 5173, local only)
pm2 restart litreview-tunnel    # cloudflared tunnel
pm2 list
```

For production UI without the script: `cd frontend && pnpm build`, then `pm2 restart litreview-api`.

## Rules

- Default `/restart` reloads API and Vite dev server; tunnel is opt-in via `--all` or `--tunnel-only`.
- After backend `src/` changes: default restart is enough; use `--backend-only` only when you want a faster API-only bounce.
- Local dev UI: Vite on 5173 via `litreview-ui`. Do not run `litreview-ui` in production; API serves `frontend/dist`.
- Do not restart tunnel unless the user asked or you changed tunnel config.
- If PM2 reports missing processes, check `ecosystem.config.js` exists (copy from `ecosystem.config.example.js`) and run `pm2 start ecosystem.config.js`.

## Related

- Script help: `./scripts/ops_pm2.sh help`
- Index: `docs/SCRIPTS.md`
- PM2 reminder rule: `.cursor/rules/core/pm2-restart.mdc`
