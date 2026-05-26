// eslint-disable-next-line react-refresh/only-export-components
export { useThemeStore as useThemeContext } from "@/lib/themeStore"

import { type ReactNode } from "react"
import { useThemeStore } from "@/lib/themeStore"

/** Ensures theme store is subscribed at app root (hydration sync). */
export function ThemeProvider({ children }: { children: ReactNode }) {
  useThemeStore()
  return children
}
