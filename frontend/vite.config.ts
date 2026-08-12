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
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${process.env.PORT ?? 8001}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (
            id.includes('highlight.js')
            || id.includes('lowlight')
            || id.includes('react-markdown')
            || id.includes('/remark-')
            || id.includes('/rehype-')
            || id.includes('/unified/')
            || id.includes('/mdast-')
            || id.includes('/hast-')
            || id.includes('/micromark')
          ) {
            return 'markdown-vendor'
          }
        },
      },
    },
  },
}))
