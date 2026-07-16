const path = require('path')

// Resolved automatically from repo root; copy to ecosystem.config.js (gitignored).
const PROJECT_DIR = path.resolve(__dirname)

// Production vs development:
// - Production: litreview-api serves frontend/dist on port 8001. Do NOT run litreview-ui
//   under PM2 in production (the Vite dev server is dev-only; serving dist avoids port
//   5173 and stale dev-proxy confusion). Deploy: make deploy-prod or scripts/deploy_prod.sh
// - Development: optionally start litreview-ui for Vite on 5173 (hot reload); API on 8001.
//
// PM2 restart policy: handles crash exits PM2 can observe.
// HTTP liveness watchdog (scripts/pm2_health_watchdog.sh) handles zombie / hung states
// by probing GET http://127.0.0.1:8001/api/health and rate-limiting pm2 restarts.
const RESTART_POLICY = {
  autorestart: true,
  watch: false,
  min_uptime: '10s',
  max_restarts: 15,
  restart_delay: 4000,
  exp_backoff_restart_delay: 100,
  kill_timeout: 8000,
  listen_timeout: 15000,
}

// API graceful shutdown: allow in-flight HTTP and workflow teardown before SIGKILL.
const API_RESTART_POLICY = {
  ...RESTART_POLICY,
  kill_timeout: 45000,
}

module.exports = {
  apps: [
    {
      name: 'litreview-api',
      script: `${PROJECT_DIR}/.venv/bin/uvicorn`,
      args: 'src.web.app:app --host 127.0.0.1 --port 8001',
      cwd: PROJECT_DIR,
      interpreter: 'none',
      exec_mode: 'fork',
      env: { PORT: '8001' },
      max_memory_restart: '2G',
      error_file: `${process.env.HOME}/.cloudflared/litreview-error.log`,
      out_file: `${process.env.HOME}/.cloudflared/litreview.log`,
      ...API_RESTART_POLICY,
    },
    {
      name: 'litreview-tunnel',
      script: '/opt/homebrew/bin/cloudflared',
      args: `tunnel --config ${PROJECT_DIR}/cloudflared-config-litreview.yml run`,
      cwd: PROJECT_DIR,
      error_file: `${process.env.HOME}/.pm2/logs/litreview-tunnel-error.log`,
      out_file: `${process.env.HOME}/.pm2/logs/litreview-tunnel-out.log`,
      max_memory_restart: '512M',
      ...RESTART_POLICY,
    },
    {
      name: 'litreview-ui',
      // Dev-only Vite dev server. Omit from PM2 in production when API serves dist.
      // Intentionally autorestart: false so a crashed dev server does not loop-restart
      // under PM2 while you are debugging locally.
      script: 'pnpm',
      args: 'dev --port 5173 --host 0.0.0.0',
      cwd: `${PROJECT_DIR}/frontend`,
      interpreter: 'none',
      exec_mode: 'fork',
      autorestart: false,
      watch: false,
    },
  ],
}
