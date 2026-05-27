import { useSyncExternalStore } from "react"
import {
  applyTheme,
  getPreferredTheme,
  persistTheme,
  type Theme,
} from "@/lib/theme"

function readThemeFromDocument(): Theme | null {
  if (typeof document === "undefined") return null
  const dom = document.documentElement.dataset.theme
  if (dom === "light" || dom === "dark") return dom
  return null
}

let theme: Theme = readThemeFromDocument() ?? getPreferredTheme()
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) {
    listener()
  }
}

export function getTheme(): Theme {
  return theme
}

export function setTheme(next: Theme): void {
  const changed = next !== theme
  theme = next
  applyTheme(next)
  persistTheme(next)
  if (changed) emit()
}

export function toggleTheme(): void {
  // Derive from live DOM first to avoid stale module state during HMR/session drift.
  const current = readThemeFromDocument() ?? theme
  setTheme(current === "dark" ? "light" : "dark")
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useThemeStore() {
  const current = useSyncExternalStore(subscribe, getTheme, () => "dark" as Theme)
  return {
    theme: current,
    setTheme,
    toggleTheme,
    isLight: current === "light",
  }
}
