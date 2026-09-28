import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "react-router-dom"
import type { ActiveFilter } from "@/components/database/FilterChipBar"
import { FACET_NONE, type PapersQuery, type PapersSort, type PapersSortKey } from "@/lib/api/db"
import { decodeHtmlEntities, humanizeSnake } from "@/lib/humanize"

export const PAGE_SIZE_OPTIONS = [50, 100, 250] as const
export type PageSize = (typeof PAGE_SIZE_OPTIONS)[number]
export const DEFAULT_PAGE_SIZE: PageSize = 50

export type MultiFacetKey = "ta" | "ft" | "primaryStatus" | "source" | "country"

export interface DbTableState {
  filters: PapersQuery
  sort: PapersSort
  page: number
  pageSize: PageSize
}

export const EMPTY_PAPERS_QUERY: PapersQuery = {
  title: "",
  author: "",
  ta: [],
  ft: [],
  primaryStatus: [],
  source: [],
  country: [],
  yearMin: null,
  yearMax: null,
}

const SORT_KEYS = new Set<PapersSortKey>([
  "title",
  "year",
  "source",
  "ta_decision",
  "ft_decision",
  "primary_status",
  "confidence",
])

const MULTI_PARAM: Record<MultiFacetKey, string> = {
  ta: "ta",
  ft: "ft",
  primaryStatus: "ps",
  source: "src",
  country: "country",
}

/** Every search param this hook owns; anything else in the URL is left untouched. */
export const DB_URL_KEYS = [
  "title",
  "author",
  ...Object.values(MULTI_PARAM),
  "ymin",
  "ymax",
  "sort",
  "dir",
  "page",
  "size",
] as const

function parseYear(raw: string | null): number | null {
  if (!raw) return null
  const n = Number.parseInt(raw, 10)
  return Number.isFinite(n) ? n : null
}

export function parseDbSearchParams(sp: URLSearchParams): DbTableState {
  const filters: PapersQuery = {
    ...EMPTY_PAPERS_QUERY,
    title: sp.get("title") ?? "",
    author: sp.get("author") ?? "",
    yearMin: parseYear(sp.get("ymin")),
    yearMax: parseYear(sp.get("ymax")),
  }
  for (const [key, param] of Object.entries(MULTI_PARAM) as Array<[MultiFacetKey, string]>) {
    filters[key] = sp.getAll(param).filter(Boolean)
  }
  const rawSort = sp.get("sort")
  const sort = rawSort && SORT_KEYS.has(rawSort as PapersSortKey) ? (rawSort as PapersSortKey) : null
  const dir = sp.get("dir") === "asc" ? "asc" : "desc"
  const page = Math.max(0, (Number.parseInt(sp.get("page") ?? "1", 10) || 1) - 1)
  const rawSize = Number.parseInt(sp.get("size") ?? "", 10)
  const pageSize = (PAGE_SIZE_OPTIONS as readonly number[]).includes(rawSize)
    ? (rawSize as PageSize)
    : DEFAULT_PAGE_SIZE
  return { filters, sort: { sort, dir: sort ? dir : "desc" }, page, pageSize }
}

/** Write table state into a copy of `base`, preserving params this hook doesn't own. */
export function writeDbSearchParams(base: URLSearchParams, state: DbTableState): URLSearchParams {
  const next = new URLSearchParams(base)
  for (const key of DB_URL_KEYS) next.delete(key)
  const { filters, sort, page, pageSize } = state
  if (filters.title) next.set("title", filters.title)
  if (filters.author) next.set("author", filters.author)
  for (const [key, param] of Object.entries(MULTI_PARAM) as Array<[MultiFacetKey, string]>) {
    for (const v of filters[key]) next.append(param, v)
  }
  if (filters.yearMin != null) next.set("ymin", String(filters.yearMin))
  if (filters.yearMax != null) next.set("ymax", String(filters.yearMax))
  if (sort.sort) {
    next.set("sort", sort.sort)
    next.set("dir", sort.dir)
  }
  if (page > 0) next.set("page", String(page + 1))
  if (pageSize !== DEFAULT_PAGE_SIZE) next.set("size", String(pageSize))
  return next
}

export function hasDbSearchParams(sp: URLSearchParams): boolean {
  return DB_URL_KEYS.some((key) => sp.has(key))
}

/** Unsorted -> asc -> desc -> unsorted (server default order). */
export function nextSort(current: PapersSort, key: PapersSortKey): PapersSort {
  if (current.sort !== key) return { sort: key, dir: "asc" }
  if (current.dir === "asc") return { sort: key, dir: "desc" }
  return { sort: null, dir: "desc" }
}

export function toggleFacetValue(values: string[], value: string): string[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value]
}

export function countActiveFilters(filters: PapersQuery): number {
  let n = 0
  if (filters.title) n += 1
  if (filters.author) n += 1
  if (filters.yearMin != null || filters.yearMax != null) n += 1
  for (const key of Object.keys(MULTI_PARAM) as MultiFacetKey[]) n += filters[key].length
  return n
}

export const FACET_LABELS: Record<MultiFacetKey, string> = {
  ta: "Title/abstract",
  ft: "Full text",
  primaryStatus: "Primary status",
  source: "Source",
  country: "Country",
}

const NONE_LABELS: Record<MultiFacetKey, string> = {
  ta: "Not screened",
  ft: "Not reached",
  primaryStatus: "Unknown",
  source: "None",
  country: "None",
}

export function facetValueLabel(key: MultiFacetKey, value: string): string {
  if (value === FACET_NONE) return NONE_LABELS[key]
  if (key === "ta" || key === "ft" || key === "primaryStatus") return humanizeSnake(value)
  return value
}

export function buildFilterChips(filters: PapersQuery): ActiveFilter[] {
  const chips: ActiveFilter[] = []
  if (filters.title) chips.push({ id: "title", label: "Title", value: decodeHtmlEntities(filters.title) })
  if (filters.author) chips.push({ id: "author", label: "Authors", value: filters.author })
  if (filters.yearMin != null || filters.yearMax != null) {
    const value =
      filters.yearMin != null && filters.yearMax != null
        ? filters.yearMin === filters.yearMax
          ? String(filters.yearMin)
          : `${filters.yearMin}–${filters.yearMax}`
        : filters.yearMin != null
          ? `${filters.yearMin} or later`
          : `${filters.yearMax} or earlier`
    chips.push({ id: "year", label: "Year", value })
  }
  for (const key of Object.keys(MULTI_PARAM) as MultiFacetKey[]) {
    for (const v of filters[key]) {
      chips.push({ id: `${key}:${v}`, label: FACET_LABELS[key], value: facetValueLabel(key, v) })
    }
  }
  return chips
}

export function removeFilterById(filters: PapersQuery, id: string): PapersQuery {
  if (id === "title") return { ...filters, title: "" }
  if (id === "author") return { ...filters, author: "" }
  if (id === "year") return { ...filters, yearMin: null, yearMax: null }
  const sep = id.indexOf(":")
  if (sep < 0) return filters
  const key = id.slice(0, sep) as MultiFacetKey
  const value = id.slice(sep + 1)
  if (!(key in MULTI_PARAM)) return filters
  return { ...filters, [key]: filters[key].filter((v) => v !== value) }
}

function storageKey(runId: string): string {
  return `dbTable:${runId}`
}

function readStored(runId: string): string {
  try {
    return sessionStorage.getItem(storageKey(runId)) ?? ""
  } catch {
    return ""
  }
}

function writeStored(runId: string, search: URLSearchParams): void {
  try {
    const own = new URLSearchParams()
    for (const key of DB_URL_KEYS) for (const v of search.getAll(key)) own.append(key, v)
    sessionStorage.setItem(storageKey(runId), own.toString())
  } catch {
    // storage unavailable: URL state still works
  }
}

/**
 * Data tab table state (filters, sort, page, page size) synced to URL search params.
 * A per-run sessionStorage copy restores the view when a tab switch drops the query string.
 */
export function useDbFilters(runId: string) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [titleSuggestQuery, setTitleSuggestQuery] = useState("")
  const [authorSuggestQuery, setAuthorSuggestQuery] = useState("")

  const searchKey = searchParams.toString()
  const state = useMemo(() => parseDbSearchParams(new URLSearchParams(searchKey)), [searchKey])

  useEffect(() => {
    const current = new URLSearchParams(searchKey)
    if (hasDbSearchParams(current)) return
    const stored = readStored(runId)
    if (!stored) return
    const restored = new URLSearchParams(current)
    for (const [k, v] of new URLSearchParams(stored)) restored.append(k, v)
    setSearchParams(restored, { replace: true })
  }, [runId, searchKey, setSearchParams])

  const commit = useCallback(
    (update: (prev: DbTableState) => DbTableState) => {
      setSearchParams(
        (prev) => {
          const current = parseDbSearchParams(prev)
          const updated = update(current)
          if (updated === current) return prev
          const next = writeDbSearchParams(prev, updated)
          writeStored(runId, next)
          return next
        },
        { replace: true },
      )
    },
    [runId, setSearchParams],
  )

  const setFilters = useCallback(
    (update: (prev: PapersQuery) => PapersQuery) =>
      commit((prev) => {
        const filters = update(prev.filters)
        return filters === prev.filters ? prev : { ...prev, filters, page: 0 }
      }),
    [commit],
  )

  const setTitleFilter = useCallback(
    (title: string) => setFilters((f) => (f.title === title ? f : { ...f, title })),
    [setFilters],
  )
  const setAuthorFilter = useCallback(
    (author: string) => setFilters((f) => (f.author === author ? f : { ...f, author })),
    [setFilters],
  )
  const toggleFacet = useCallback(
    (key: MultiFacetKey, value: string) =>
      setFilters((f) => ({ ...f, [key]: toggleFacetValue(f[key], value) })),
    [setFilters],
  )
  const clearFacet = useCallback(
    (key: MultiFacetKey) => setFilters((f) => ({ ...f, [key]: [] })),
    [setFilters],
  )
  const setYearRange = useCallback(
    (yearMin: number | null, yearMax: number | null) =>
      setFilters((f) => ({ ...f, yearMin, yearMax })),
    [setFilters],
  )
  const removeFilter = useCallback(
    (id: string) => {
      if (id === "title") setTitleSuggestQuery("")
      if (id === "author") setAuthorSuggestQuery("")
      setFilters((f) => removeFilterById(f, id))
    },
    [setFilters],
  )
  const clearAllFilters = useCallback(() => {
    setTitleSuggestQuery("")
    setAuthorSuggestQuery("")
    setFilters(() => EMPTY_PAPERS_QUERY)
  }, [setFilters])

  const toggleSort = useCallback(
    (key: PapersSortKey) => commit((prev) => ({ ...prev, sort: nextSort(prev.sort, key), page: 0 })),
    [commit],
  )
  const setPage = useCallback(
    (page: number) => commit((prev) => ({ ...prev, page: Math.max(0, page) })),
    [commit],
  )
  const setPageSize = useCallback(
    (pageSize: PageSize) => commit((prev) => ({ ...prev, pageSize, page: 0 })),
    [commit],
  )

  const activeFilterChips = useMemo(() => buildFilterChips(state.filters), [state.filters])

  return {
    ...state,
    activeFilterCount: countActiveFilters(state.filters),
    activeFilterChips,
    setTitleFilter,
    setAuthorFilter,
    toggleFacet,
    clearFacet,
    setYearRange,
    removeFilter,
    clearAllFilters,
    toggleSort,
    setPage,
    setPageSize,
    titleSuggestQuery,
    setTitleSuggestQuery,
    authorSuggestQuery,
    setAuthorSuggestQuery,
  }
}
