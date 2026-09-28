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
          const pkg = packageName(id)
          return pkg ? vendorChunk(pkg) : undefined
        },
      },
    },
  },
}))

/** npm package name for a node_modules module id (handles pnpm's nested layout). */
function packageName(id: string): string | null {
  const marker = '/node_modules/'
  const idx = id.lastIndexOf(marker)
  if (idx === -1) return null
  const parts = id.slice(idx + marker.length).split('/')
  return parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0]
}

const REACT_PACKAGES = new Set(['react', 'react-dom', 'scheduler', 'react-router', 'react-router-dom'])

/** Shared by the app shell and recharts; pinned here so they do not drag charts into first paint. */
const UI_PACKAGES = new Set(['clsx', 'tailwind-merge', 'class-variance-authority'])

const CHART_PACKAGES = new Set([
  'recharts',
  'victory-vendor',
  'internmap',
  'decimal.js-light',
  'es-toolkit',
  'redux',
  'redux-thunk',
  'react-redux',
  'reselect',
  'immer',
  '@reduxjs/toolkit',
])

const MARKDOWN_PACKAGES = new Set([
  'react-markdown',
  'unified',
  'bail',
  'trough',
  'devlop',
  'extend',
  'is-plain-obj',
  'property-information',
  'space-separated-tokens',
  'comma-separated-tokens',
  'html-url-attributes',
  'inline-style-parser',
  'style-to-object',
  'style-to-js',
  'estree-util-is-identifier-name',
  'decode-named-character-reference',
  'trim-lines',
  'ccount',
  'escape-string-regexp',
  'longest-streak',
  'markdown-table',
  'zwitch',
  'github-slugger',
  '@ungap/structured-clone',
])

const MARKDOWN_PREFIXES = ['remark-', 'rehype-', 'mdast-', 'hast-', 'hastscript', 'micromark', 'unist-', 'vfile']

function vendorChunk(pkg: string): string | undefined {
  if (REACT_PACKAGES.has(pkg)) return 'react-vendor'
  if (pkg.startsWith('@radix-ui/') || pkg.startsWith('@floating-ui/')) return 'radix-vendor'
  if (UI_PACKAGES.has(pkg)) return 'radix-vendor'
  if (pkg.startsWith('@tanstack/')) return 'tanstack-vendor'
  if (CHART_PACKAGES.has(pkg) || pkg.startsWith('d3-')) return 'charts-vendor'
  if (pkg === 'highlight.js' || pkg === 'lowlight') return 'highlight-vendor'
  if (MARKDOWN_PACKAGES.has(pkg) || MARKDOWN_PREFIXES.some((p) => pkg.startsWith(p))) return 'markdown-vendor'
  return undefined
}
