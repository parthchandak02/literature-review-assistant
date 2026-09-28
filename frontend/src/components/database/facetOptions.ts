import { facetValueLabel, type MultiFacetKey } from "@/hooks/useDbFilters"
import { FACET_NONE, type PapersFacetField, type PapersFacets } from "@/lib/api/db"

export interface FacetOption {
  value: string
  label: string
  count: number
}

export const FACET_FIELD: Record<MultiFacetKey, PapersFacetField> = {
  ta: "ta_decision",
  ft: "ft_decision",
  primaryStatus: "primary_status",
  source: "source",
  country: "country",
}

/** Facet menu rows: server counts (null mapped to the none sentinel), plus selected values now at zero. */
export function facetOptions(
  key: MultiFacetKey,
  facets: PapersFacets | undefined,
  selected: string[],
): FacetOption[] {
  const counts = facets?.counts?.[FACET_FIELD[key]] ?? []
  const options: FacetOption[] = counts.map((c) => {
    const value = c.value == null || c.value === "" ? FACET_NONE : String(c.value)
    return { value, label: facetValueLabel(key, value), count: c.count }
  })
  for (const value of selected) {
    if (!options.some((o) => o.value === value)) {
      options.push({ value, label: facetValueLabel(key, value), count: 0 })
    }
  }
  return options
}
