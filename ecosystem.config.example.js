const PROJECT_DIR = '/absolute/path/to/literature-review-assistant'

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
      autorestart: true,
      watch: false,
      max_memory_restart: '2G',
      error_file: `${process.env.HOME}/.cloudflared/litreview-error.log`,
      out_file: `${process.env.HOME}/.cloudflared/litreview.log`,
    },
    {
      name: 'litreview-tunnel',
      script: '/opt/homebrew/bin/cloudflared',
      args: `tunnel --config ${PROJECT_DIR}/cloudflared-config-litreview.yml run`,
      cwd: PROJECT_DIR,
      autorestart: true,
      watch: false,
    },
    {
      name: 'litreview-ui',
      script: 'pnpm',
      args: 'dev --port 5173',
      cwd: `${PROJECT_DIR}/frontend`,
      interpreter: 'none',
      exec_mode: 'fork',
      autorestart: false,
      watch: false,
    },
  ],
}
