import { useCallback, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchScreeningSummary } from "@/lib/api"
import type { ScreeningOverride } from "@/lib/api"

export function screeningSummaryQueryKey(runId: string) {
  return ["screeningSummary", runId] as const
}

export function useScreeningSummary(runId: string) {
  return useQuery({
    queryKey: screeningSummaryQueryKey(runId),
    queryFn: () => fetchScreeningSummary(runId),
    enabled: Boolean(runId),
    staleTime: 30_000,
  })
}

export function screeningOverridesStorageKey(scopeId: string) {
  return `litreview-screening-overrides:${scopeId}`
}

function readOverrides(storageKey: string): Map<string, ScreeningOverride> {
  try {
    const raw = sessionStorage.getItem(storageKey)
    if (!raw) return new Map()
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return new Map()
    const entries = parsed.filter(
      (o): o is ScreeningOverride =>
        typeof o === "object" &&
        o !== null &&
        typeof (o as ScreeningOverride).paper_id === "string" &&
        ((o as ScreeningOverride).decision === "include" ||
          (o as ScreeningOverride).decision === "exclude"),
    )
    return new Map(entries.map((o) => [o.paper_id, o]))
  } catch {
    return new Map()
  }
}

function writeOverrides(storageKey: string, overrides: Map<string, ScreeningOverride>) {
  try {
    if (overrides.size === 0) {
      sessionStorage.removeItem(storageKey)
    } else {
      sessionStorage.setItem(storageKey, JSON.stringify(Array.from(overrides.values())))
    }
  } catch {
    // sessionStorage unavailable (private mode / quota); keep in-memory state only
  }
}

export function useScreeningOverrides(scopeId: string) {
  const storageKey = screeningOverridesStorageKey(scopeId)
  const [overrides, setOverrides] = useState(() => readOverrides(storageKey))

  const setOverride = useCallback(
    (paperId: string, override: ScreeningOverride | null) => {
      setOverrides((prev) => {
        const next = new Map(prev)
        if (override === null) next.delete(paperId)
        else next.set(paperId, override)
        writeOverrides(storageKey, next)
        return next
      })
    },
    [storageKey],
  )

  const clearOverrides = useCallback(() => {
    writeOverrides(storageKey, new Map())
    setOverrides(new Map())
  }, [storageKey])

  return { overrides, setOverride, clearOverrides }
}
