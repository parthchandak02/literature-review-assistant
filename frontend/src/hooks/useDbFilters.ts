import { useEffect, useMemo, useReducer, useState } from "react"
import type { ActiveFilter } from "@/components/database/FilterChipBar"
import type { DbPapersFilters } from "@/hooks/useDbPapers"

export type PaperFilterId =
  | "title"
  | "author"
  | "year"
  | "source"
  | "country"
  | "ta"
  | "ft"
  | "primaryStatus"

export type PapersPaginationState = {
  filterSignature: string
  runId: string
  page: number
}

type PapersPaginationAction =
  | { type: "set_page"; page: number }
  | { type: "sync_scope"; filterSignature: string; runId: string }

export function papersPaginationReducer(
  state: PapersPaginationState,
  action: PapersPaginationAction,
): PapersPaginationState {
  switch (action.type) {
    case "set_page":
      return { ...state, page: action.page }
    case "sync_scope":
      if (state.filterSignature === action.filterSignature && state.runId === action.runId) {
        return state
      }
      return {
        filterSignature: action.filterSignature,
        runId: action.runId,
        page: 0,
      }
    default:
      return state
  }
}

export function buildFilterSignature(filters: DbPapersFilters): string {
  return [
    filters.titleFilter,
    filters.authorFilter,
    filters.taFilter,
    filters.ftFilter,
    filters.primaryStatusFilter,
    filters.yearFilter,
    filters.sourceFilter,
    filters.countryFilter,
  ].join("\0")
}

const EMPTY_FILTERS: DbPapersFilters = {
  titleFilter: "",
  authorFilter: "",
  taFilter: "",
  ftFilter: "",
  primaryStatusFilter: "",
  yearFilter: "",
  sourceFilter: "",
  countryFilter: "",
}

/** Page used for the papers query; coerces to 0 until pagination state syncs after filter/run changes. */
export function resolveQueryPage(
  pagination: PapersPaginationState,
  filterSignature: string,
  runId: string,
): number {
  if (pagination.filterSignature !== filterSignature || pagination.runId !== runId) {
    return 0
  }
  return pagination.page
}

/** True only for the unfiltered first page; gates facet inclusion on the papers query. */
export function isDbInitialQuery(queryPage: number, filters: DbPapersFilters): boolean {
  if (queryPage !== 0) return false
  return buildFilterSignature(filters) === buildFilterSignature(EMPTY_FILTERS)
}

export function useDbFilters(runId: string) {
  const [titleFilter, setTitleFilter] = useState("")
  const [authorFilter, setAuthorFilter] = useState("")
  const [taFilter, setTaFilter] = useState("")
  const [ftFilter, setFtFilter] = useState("")
  const [primaryStatusFilter, setPrimaryStatusFilter] = useState("")
  const [yearFilter, setYearFilter] = useState("")
  const [sourceFilter, setSourceFilter] = useState("")
  const [countryFilter, setCountryFilter] = useState("")
  const [titleSuggestQuery, setTitleSuggestQuery] = useState("")
  const [authorSuggestQuery, setAuthorSuggestQuery] = useState("")

  const filters = useMemo<DbPapersFilters>(
    () => ({
      titleFilter,
      authorFilter,
      taFilter,
      ftFilter,
      primaryStatusFilter,
      yearFilter,
      sourceFilter,
      countryFilter,
    }),
    [
      titleFilter,
      authorFilter,
      taFilter,
      ftFilter,
      primaryStatusFilter,
      yearFilter,
      sourceFilter,
      countryFilter,
    ],
  )

  const filterSignature = useMemo(() => buildFilterSignature(filters), [filters])

  const [pagination, dispatchPagination] = useReducer(papersPaginationReducer, {
    filterSignature,
    runId,
    page: 0,
  })

  useEffect(() => {
    dispatchPagination({ type: "sync_scope", filterSignature, runId })
  }, [filterSignature, runId])

  const queryPage = resolveQueryPage(pagination, filterSignature, runId)
  const isInitialQuery = isDbInitialQuery(queryPage, filters)

  const clearAllFilters = () => {
    setTitleFilter("")
    setAuthorFilter("")
    setTaFilter("")
    setFtFilter("")
    setPrimaryStatusFilter("")
    setYearFilter("")
    setSourceFilter("")
    setCountryFilter("")
    setTitleSuggestQuery("")
    setAuthorSuggestQuery("")
  }

  const activeFilterChips = useMemo<ActiveFilter[]>(() => {
    const chips: ActiveFilter[] = []
    if (titleFilter) chips.push({ id: "title", label: "Title", value: titleFilter })
    if (authorFilter) chips.push({ id: "author", label: "Authors", value: authorFilter })
    if (yearFilter) chips.push({ id: "year", label: "Year", value: yearFilter })
    if (sourceFilter) chips.push({ id: "source", label: "Source", value: sourceFilter })
    if (countryFilter) chips.push({ id: "country", label: "Country", value: countryFilter })
    if (taFilter) chips.push({ id: "ta", label: "Title/Abstract", value: taFilter })
    if (ftFilter) chips.push({ id: "ft", label: "Full-Text", value: ftFilter })
    if (primaryStatusFilter) {
      chips.push({ id: "primaryStatus", label: "Primary Status", value: primaryStatusFilter })
    }
    return chips
  }, [
    titleFilter,
    authorFilter,
    yearFilter,
    sourceFilter,
    countryFilter,
    taFilter,
    ftFilter,
    primaryStatusFilter,
  ])

  const removeFilter = (id: string) => {
    switch (id as PaperFilterId) {
      case "title":
        setTitleFilter("")
        setTitleSuggestQuery("")
        break
      case "author":
        setAuthorFilter("")
        setAuthorSuggestQuery("")
        break
      case "year":
        setYearFilter("")
        break
      case "source":
        setSourceFilter("")
        break
      case "country":
        setCountryFilter("")
        break
      case "ta":
        setTaFilter("")
        break
      case "ft":
        setFtFilter("")
        break
      case "primaryStatus":
        setPrimaryStatusFilter("")
        break
    }
  }

  return {
    filters,
    filterSignature,
    queryPage,
    dispatchPagination,
    isInitialQuery,
    titleFilter,
    setTitleFilter,
    authorFilter,
    setAuthorFilter,
    taFilter,
    setTaFilter,
    ftFilter,
    setFtFilter,
    primaryStatusFilter,
    setPrimaryStatusFilter,
    yearFilter,
    setYearFilter,
    sourceFilter,
    setSourceFilter,
    countryFilter,
    setCountryFilter,
    titleSuggestQuery,
    setTitleSuggestQuery,
    authorSuggestQuery,
    setAuthorSuggestQuery,
    activeFilterChips,
    clearAllFilters,
    removeFilter,
  }
}
