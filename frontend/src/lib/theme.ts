export type Theme = "dark" | "light"

export const THEME_STORAGE_KEY = "litreview-theme"

export function getStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === "light" || stored === "dark") return stored
  } catch {
    /* private browsing / blocked storage */
  }
  return null
}

export function getPreferredTheme(): Theme {
  const stored = getStoredTheme()
  if (stored) return stored
  if (typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light"
  }
  return "dark"
}

export function applyTheme(theme: Theme): void {
  const resolved = theme === "light" ? "light" : "dark"
  document.documentElement.dataset.theme = resolved
  document.documentElement.style.colorScheme = resolved
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) {
    meta.setAttribute("content", theme === "light" ? "#f3f3f3" : "#7c3aed")
  }
}

export function persistTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    /* ignore */
  }
}
