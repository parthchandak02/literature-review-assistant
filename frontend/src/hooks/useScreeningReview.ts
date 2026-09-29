import { useCallback, useEffect, useMemo, useReducer, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchScreeningSummary } from "@/lib/api"
import { automationBreakdown } from "@/lib/automationSteps"
import type { ScreenedPaper, ScreeningOverride, ScreeningSummary } from "@/lib/api"
import {
  buildRows,
  countFilterTabs,
  countFinalDecisions,
  isAutomationRow,
  selectVisibleRows,
  type AiDecision,
  type HumanDecision,
  type OverrideMap,
  type ScreeningFilter,
  type ScreeningSort,
} from "@/components/screening/screeningModel"

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

/** Papers the gate will send to extraction (include + uncertain final decisions). */
export function countPendingScreening(summary: ScreeningSummary | undefined): number | null {
  if (!summary) return null
  let n = 0
  for (const paper of summary.papers) {
    const decision = paper.final_decision ?? paper.decision
    if (decision === "include" || decision === "uncertain") n += 1
  }
  return n
}

/** Include + uncertain count for the gate banner, or null while unknown. Shares the summary cache. */
export function useScreeningPendingCount(runId: string | null | undefined, enabled = true): number | null {
  const query = useQuery({
    queryKey: screeningSummaryQueryKey(runId ?? ""),
    queryFn: () => fetchScreeningSummary(runId ?? ""),
    enabled: enabled && Boolean(runId),
    staleTime: 30_000,
    select: countPendingScreening,
  })
  return query.data ?? null
}

export function screeningOverridesStorageKey(scopeId: string) {
  return `litreview-screening-overrides:${scopeId}`
}

export function readOverrides(storageKey: string): Map<string, ScreeningOverride> {
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

function writeOverrides(storageKey: string, overrides: OverrideMap) {
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

export const UNDO_LIMIT = 200

export interface ReviewState {
  overrides: OverrideMap
  undoStack: OverrideMap[]
  focusedKey: string | null
  expanded: ReadonlySet<string>
  selected: ReadonlySet<string>
  reviewed: ReadonlySet<string>
  filter: ScreeningFilter
  search: string
  sort: ScreeningSort
  filterBasis: OverrideMap
}

export interface DecisionTarget {
  key: string
  ai: AiDecision
}

export type ReviewAction =
  | { type: "decide"; targets: DecisionTarget[]; decision: HumanDecision }
  | { type: "clearOverrides"; keys: string[] }
  | { type: "setReason"; key: string; reason: string }
  | { type: "undo" }
  | { type: "resetOverrides" }
  | { type: "hydrate"; overrides: OverrideMap }
  | { type: "focus"; key: string | null }
  | { type: "toggleExpanded"; key: string }
  | { type: "toggleSelected"; key: string }
  | { type: "setSelected"; keys: string[]; selected: boolean }
  | { type: "clearSelection" }
  | { type: "setFilter"; filter: ScreeningFilter }
  | { type: "setSearch"; search: string }
  | { type: "setSort"; sort: ScreeningSort }

export function initialReviewState(overrides: OverrideMap = new Map()): ReviewState {
  return {
    overrides,
    undoStack: [],
    focusedKey: null,
    expanded: new Set(),
    selected: new Set(),
    reviewed: new Set(),
    filter: "all",
    search: "",
    sort: "confidence-asc",
    filterBasis: overrides,
  }
}

function withAdded(set: ReadonlySet<string>, keys: Iterable<string>): ReadonlySet<string> {
  let next: Set<string> | null = null
  for (const key of keys) {
    if (set.has(key) || next?.has(key)) continue
    next ??= new Set(set)
    next.add(key)
  }
  return next ?? set
}

function commitOverrides(state: ReviewState, next: Map<string, ScreeningOverride>, touched: string[]): ReviewState {
  const undoStack = [...state.undoStack, state.overrides]
  if (undoStack.length > UNDO_LIMIT) undoStack.shift()
  return { ...state, overrides: next, undoStack, reviewed: withAdded(state.reviewed, touched) }
}

/**
 * A decision that matches the AI clears any override; the opposite decision creates one.
 * Uncertain papers have no AI include/exclude, so either decision creates an override.
 */
export function applyDecision(
  overrides: OverrideMap,
  targets: DecisionTarget[],
  decision: HumanDecision,
): Map<string, ScreeningOverride> | null {
  let next: Map<string, ScreeningOverride> | null = null
  for (const { key, ai } of targets) {
    const current = overrides.get(key)
    if (ai === decision) {
      if (!current) continue
      next ??= new Map(overrides)
      next.delete(key)
    } else if (current?.decision !== decision) {
      next ??= new Map(overrides)
      next.set(key, current?.reason ? { paper_id: key, decision, reason: current.reason } : { paper_id: key, decision })
    }
  }
  return next
}

export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case "decide": {
      const next = applyDecision(state.overrides, action.targets, action.decision)
      const touched = action.targets.map((t) => t.key)
      if (!next) return { ...state, reviewed: withAdded(state.reviewed, touched) }
      return commitOverrides(state, next, touched)
    }
    case "clearOverrides": {
      const keys = action.keys.filter((k) => state.overrides.has(k))
      if (keys.length === 0) return state
      const next = new Map(state.overrides)
      for (const key of keys) next.delete(key)
      return commitOverrides(state, next, keys)
    }
    case "setReason": {
      const current = state.overrides.get(action.key)
      if (!current) return state
      const reason = action.reason
      if ((current.reason ?? "") === reason) return state
      const next = new Map(state.overrides)
      next.set(action.key, reason ? { ...current, reason } : { paper_id: current.paper_id, decision: current.decision })
      return { ...state, overrides: next }
    }
    case "undo": {
      if (state.undoStack.length === 0) return state
      const undoStack = state.undoStack.slice(0, -1)
      return { ...state, overrides: state.undoStack[state.undoStack.length - 1], undoStack }
    }
    case "hydrate":
      return { ...state, overrides: action.overrides, undoStack: [], filterBasis: action.overrides }
    case "resetOverrides":
      if (state.overrides.size === 0 && state.undoStack.length === 0) return state
      return { ...state, overrides: new Map(), undoStack: [], filterBasis: new Map() }
    case "focus":
      if (state.focusedKey === action.key) return state
      return { ...state, focusedKey: action.key }
    case "toggleExpanded": {
      const expanded = new Set(state.expanded)
      if (expanded.has(action.key)) expanded.delete(action.key)
      else expanded.add(action.key)
      return {
        ...state,
        expanded,
        focusedKey: action.key,
        reviewed: withAdded(state.reviewed, [action.key]),
      }
    }
    case "toggleSelected": {
      const selected = new Set(state.selected)
      if (selected.has(action.key)) selected.delete(action.key)
      else selected.add(action.key)
      return { ...state, selected }
    }
    case "setSelected": {
      const selected = new Set(state.selected)
      for (const key of action.keys) {
        if (action.selected) selected.add(key)
        else selected.delete(key)
      }
      return { ...state, selected }
    }
    case "clearSelection":
      if (state.selected.size === 0) return state
      return { ...state, selected: new Set() }
    case "setFilter":
      return { ...state, filter: action.filter, filterBasis: state.overrides }
    case "setSearch":
      return { ...state, search: action.search, filterBasis: state.overrides }
    case "setSort":
      return { ...state, sort: action.sort, filterBasis: state.overrides }
  }
}

/** Next focus target for j/k style movement; clamps at the ends. */
export function moveFocus(visibleKeys: readonly string[], current: string | null, delta: number): string | null {
  if (visibleKeys.length === 0) return null
  const index = current ? visibleKeys.indexOf(current) : -1
  if (index === -1) return delta >= 0 ? visibleKeys[0] : visibleKeys[visibleKeys.length - 1]
  const nextIndex = Math.min(visibleKeys.length - 1, Math.max(0, index + delta))
  return visibleKeys[nextIndex]
}

export function useScreeningReview(
  scopeId: string,
  papers: readonly ScreenedPaper[],
  { readOnly = false }: { readOnly?: boolean } = {},
) {
  const storageKey = screeningOverridesStorageKey(scopeId)
  const [state, dispatch] = useReducer(reviewReducer, storageKey, (key) =>
    initialReviewState(readOnly ? new Map() : readOverrides(key)),
  )

  // Overrides load from storage only once the view is editable; until then nothing is written back.
  const hydrated = useRef(!readOnly)
  useEffect(() => {
    if (!readOnly && hydrated.current) writeOverrides(storageKey, state.overrides)
  }, [readOnly, storageKey, state.overrides])
  useEffect(() => {
    if (readOnly || hydrated.current) return
    hydrated.current = true
    dispatch({ type: "hydrate", overrides: readOverrides(storageKey) })
  }, [readOnly, storageKey])

  const rows = useMemo(() => buildRows(papers), [papers])
  const aiByKey = useMemo(() => new Map(rows.map((r) => [r.key, r.paper.decision])), [rows])

  const visibleRows = useMemo(
    () =>
      selectVisibleRows(rows, {
        filter: state.filter,
        search: state.search,
        sort: state.sort,
        filterBasis: state.filterBasis,
      }),
    [rows, state.filter, state.search, state.sort, state.filterBasis],
  )
  const visibleKeys = useMemo(() => visibleRows.map((r) => r.key), [visibleRows])
  const finalCounts = useMemo(() => countFinalDecisions(rows, state.overrides), [rows, state.overrides])
  const tabCounts = useMemo(() => countFilterTabs(rows, state.overrides), [rows, state.overrides])
  const reviewedCount = useMemo(
    () =>
      rows.reduce(
        (n, r) => n + (!isAutomationRow(r) && (state.reviewed.has(r.key) || state.overrides.has(r.key)) ? 1 : 0),
        0,
      ),
    [rows, state.reviewed, state.overrides],
  )
  const automation = useMemo(() => automationBreakdown(rows.map((r) => r.automationStep)), [rows])

  const decide = useCallback(
    (keys: string[], decision: HumanDecision) => {
      const targets = keys.flatMap((key) => {
        const ai = aiByKey.get(key)
        return ai ? [{ key, ai }] : []
      })
      if (targets.length > 0) dispatch({ type: "decide", targets, decision })
    },
    [aiByKey],
  )

  const overrideList = useMemo(() => Array.from(state.overrides.values()), [state.overrides])

  return {
    state,
    dispatch,
    rows,
    visibleRows,
    visibleKeys,
    finalCounts,
    tabCounts,
    reviewedCount,
    automation,
    decide,
    overrideList,
  }
}
