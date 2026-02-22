module.exports = {
  apps: [
    {
      name: 'api',
      script: 'uv',
      args: 'run uvicorn src.web.app:app --port 8001 --reload --reload-dir src --reload-dir config',
      interpreter: 'none',
      exec_mode: 'fork',
      env: { PORT: '8001' },
      error_file: './logs/api-error.log',
      out_file: './logs/api.log',
    },
    {
      name: 'ui',
      script: 'pnpm',
      args: 'run dev -- --port 5173',
      cwd: './frontend',
      interpreter: 'none',
      exec_mode: 'fork',
      env: { PORT: '8001', UI_PORT: '5173' },
      error_file: './logs/ui-error.log',
      out_file: './logs/ui.log',
    },
  ],
}
