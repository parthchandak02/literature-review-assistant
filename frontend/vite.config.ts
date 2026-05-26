import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

/** yyyy.mm.dd.hh.mm at build time (local clock). */
function formatFrontendBuildStamp(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}.${pad(date.getHours())}.${pad(date.getMinutes())}`
}

export default defineConfig(({ command }) => ({
  define: {
    __FRONTEND_BUILD_STAMP__: JSON.stringify(
      command === 'build' ? formatFrontendBuildStamp() : '',
    ),
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.PORT ?? 8001}`,
        changeOrigin: true,
      },
    },
  },
}))
