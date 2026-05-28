import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App, { AppErrorBoundary } from './App.tsx'
import { ThemeProvider } from './context/ThemeContext.tsx'
import { QueryProvider } from './context/QueryProvider.tsx'
import { getPreferredTheme } from './lib/theme'
import { setTheme } from './lib/themeStore'

setTheme(getPreferredTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <QueryProvider>
        <ThemeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </QueryProvider>
    </AppErrorBoundary>
  </StrictMode>,
)
