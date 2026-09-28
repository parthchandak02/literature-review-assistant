import { useCallback, useEffect, useState, useSyncExternalStore } from "react"
import { APIResponseError, triggerExport } from "@/lib/api"
import { fetchManuscriptTemplateSections } from "./draftQuality"
import { formatExportError } from "./manuscriptUtils"

export type PackageStatus = "unbuilt" | "incomplete" | "building" | "ready" | "error"

export interface PackageState {
  status: PackageStatus
  files: string[]
  error: string | null
  lastForce: boolean
}

export type PackageEvent =
  | { type: "SYNC"; complete: boolean; partial: boolean }
  | { type: "BUILD"; force: boolean }
  | { type: "BUILT"; files: string[] }
  | { type: "INCOMPLETE" }
  | { type: "FAILED"; error: string }

export const INITIAL_PACKAGE_STATE: PackageState = {
  status: "unbuilt",
  files: [],
  error: null,
  lastForce: false,
}

export function packageReducer(state: PackageState, event: PackageEvent): PackageState {
  switch (event.type) {
    case "SYNC":
      if (state.status !== "unbuilt") return state
      if (event.complete) return { ...state, status: "ready" }
      if (event.partial) return { ...state, status: "incomplete" }
      return state
    case "BUILD":
      if (state.status === "building") return state
      return { ...state, status: "building", error: null, lastForce: event.force }
    case "BUILT":
      return { ...state, status: "ready", files: event.files, error: null }
    case "INCOMPLETE":
      return { ...state, status: "incomplete", error: null }
    case "FAILED":
      return { ...state, status: "error", error: event.error }
  }
}

export type PackageAction = "build" | "rebuild" | "retry" | "download"

export function primaryPackageAction(status: PackageStatus): PackageAction | null {
  switch (status) {
    case "unbuilt":
      return "build"
    case "incomplete":
      return "rebuild"
    case "error":
      return "retry"
    case "ready":
      return "download"
    case "building":
      return null
  }
}

export function forceForAction(state: PackageState, action: Exclude<PackageAction, "download">): boolean {
  if (action === "build") return false
  if (action === "rebuild") return true
  return state.lastForce
}

export function rebuildNeedsConfirm(status: PackageStatus): boolean {
  return status === "ready"
}

export const PACKAGE_ACTION_LABEL: Record<PackageAction, string> = {
  build: "Build submission package",
  rebuild: "Rebuild submission package",
  retry: "Retry build",
  download: "Download submission package",
}

const states = new Map<string, PackageState>()
const listeners = new Set<() => void>()

function getState(runId: string): PackageState {
  return states.get(runId) ?? INITIAL_PACKAGE_STATE
}

export function dispatchPackageEvent(runId: string, event: PackageEvent): PackageState {
  const prev = getState(runId)
  const next = packageReducer(prev, event)
  if (next !== prev) {
    states.set(runId, next)
    listeners.forEach((l) => l())
  }
  return next
}

export function resetPackageStore() {
  states.clear()
  listeners.forEach((l) => l())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export async function runPackageBuild(runId: string, force: boolean): Promise<PackageState> {
  if (getState(runId).status === "building") return getState(runId)
  dispatchPackageEvent(runId, { type: "BUILD", force })
  try {
    const result = await triggerExport(runId, force)
    return dispatchPackageEvent(runId, { type: "BUILT", files: result.files })
  } catch (error) {
    if (error instanceof APIResponseError && error.status === 409 && !force) {
      return dispatchPackageEvent(runId, { type: "INCOMPLETE" })
    }
    return dispatchPackageEvent(runId, {
      type: "FAILED",
      error: formatExportError(error) || "Failed to build submission package",
    })
  }
}

export async function ensureSubmissionPackage(runId: string): Promise<PackageState> {
  const current = getState(runId)
  if (current.status === "ready") return current
  let next = await runPackageBuild(runId, current.status === "incomplete")
  if (next.status === "incomplete") next = await runPackageBuild(runId, true)
  return next
}

export function useSubmissionPackage(
  runId: string | null | undefined,
  sync?: { complete: boolean; partial: boolean },
) {
  const key = runId ?? ""
  const state = useSyncExternalStore(
    subscribe,
    () => getState(key),
    () => getState(key),
  )
  const complete = sync?.complete ?? false
  const partial = sync?.partial ?? false

  useEffect(() => {
    if (!key) return
    dispatchPackageEvent(key, { type: "SYNC", complete, partial })
  }, [key, complete, partial])

  const run = useCallback(
    (action: Exclude<PackageAction, "download">) =>
      key ? runPackageBuild(key, forceForAction(getState(key), action)) : Promise.resolve(getState(key)),
    [key],
  )
  const ensure = useCallback(
    () => (key ? ensureSubmissionPackage(key) : Promise.resolve(getState(key))),
    [key],
  )

  return { state, run, ensure }
}

export interface PackagePrompt {
  /** Manuscript sections that still contain template text. */
  sections: string[]
  /** True when the build would overwrite an existing package. */
  overwrite: boolean
  proceed: () => void
}

/**
 * Confirm step in front of every package build. Checks the run's manuscript for template text and,
 * when some is found (or the build would overwrite a ready package), holds the build until confirmed.
 */
export function usePackageBuildGuard(runId: string | null | undefined) {
  const [prompt, setPrompt] = useState<PackagePrompt | null>(null)
  const [checking, setChecking] = useState(false)

  const guard = useCallback(
    async (proceed: () => void, options?: { overwrite?: boolean }) => {
      const overwrite = Boolean(options?.overwrite)
      let sections: string[] = []
      if (runId) {
        setChecking(true)
        try {
          sections = await fetchManuscriptTemplateSections(runId)
        } finally {
          setChecking(false)
        }
      }
      if (sections.length === 0 && !overwrite) {
        proceed()
        return
      }
      setPrompt({ sections, overwrite, proceed })
    },
    [runId],
  )

  const confirm = useCallback(() => {
    const pending = prompt
    setPrompt(null)
    pending?.proceed()
  }, [prompt])

  const cancel = useCallback(() => setPrompt(null), [])

  return { prompt, checking, guard, confirm, cancel }
}

export function startDownload(url: string) {
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = ""
  anchor.rel = "noopener"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
}
