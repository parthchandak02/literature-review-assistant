import { Suspense, createContext, lazy, useCallback, useContext, useMemo, useState } from "react"
import type { ReactNode } from "react"

export type SettingsTab = "keys" | "costs"

export interface SettingsContextValue {
  openSettings: (tab?: SettingsTab) => void
  /** Increments each time the Settings dialog closes; watch it to re-read keys or costs. */
  closedVersion: number
}

const SettingsContext = createContext<SettingsContextValue>({
  openSettings: () => {},
  closedVersion: 0,
})

const SettingsDialog = lazy(() =>
  import("@/components/SettingsDialog").then((m) => ({ default: m.SettingsDialog })),
)

// eslint-disable-next-line react-refresh/only-export-components
export function useSettings(): SettingsContextValue {
  return useContext(SettingsContext)
}

/** Owns the app's single Settings dialog. The dialog chunk loads on first open. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [tab, setTab] = useState<SettingsTab>("keys")
  const [closedVersion, setClosedVersion] = useState(0)

  const openSettings = useCallback((next: SettingsTab = "keys") => {
    setTab(next)
    setMounted(true)
    setOpen(true)
  }, [])

  const handleOpenChange = useCallback((next: boolean) => {
    setOpen(next)
    if (!next) setClosedVersion((v) => v + 1)
  }, [])

  const value = useMemo(() => ({ openSettings, closedVersion }), [openSettings, closedVersion])

  return (
    <SettingsContext.Provider value={value}>
      {children}
      {mounted && (
        <Suspense fallback={null}>
          <SettingsDialog open={open} onOpenChange={handleOpenChange} initialTab={tab} />
        </Suspense>
      )}
    </SettingsContext.Provider>
  )
}
