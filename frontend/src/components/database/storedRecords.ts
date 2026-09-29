import { DUPLICATE_RECORD, SUPERSEDED_RECORD } from "@/lib/automationSteps"
import type { PapersFacets, PrismaLiveCounts } from "@/lib/api/db"
import { formatCount } from "@/lib/format"

const plural = (n: number, one: string, many: string) => `${formatCount(n)} ${n === 1 ? one : many}`

function taCount(facets: PapersFacets | undefined, value: string): number {
  return facets?.counts?.ta_decision?.find((c) => c.value === value)?.count ?? 0
}

/** How the unfiltered stored-record total reconciles with PRISMA "records identified"; null when it cannot be stated. */
export function storedRecordsReconciliation(
  storedTotal: number,
  facets: PapersFacets | undefined,
  prisma: PrismaLiveCounts | null | undefined,
): string | null {
  if (!prisma || !facets?.counts) return null
  const identified = prisma.total_identified_databases + prisma.total_identified_other
  const extra = storedTotal - identified
  if (extra < 0) return null
  const superseded = taCount(facets, SUPERSEDED_RECORD)
  const duplicates = taCount(facets, DUPLICATE_RECORD)
  let equation = `${plural(storedTotal, "stored record", "stored records")} = ${formatCount(identified)} identified in PRISMA`
  const notes: string[] = []
  if (extra > 0 && extra === superseded) {
    equation += ` + ${plural(superseded, "superseded search result", "superseded search results")}`
    notes.push(
      "A superseded result came from a connector's first search, which a broader retry replaced. It stays in the database, but PRISMA counts only the retry.",
    )
  } else if (extra > 0) {
    equation += ` + ${plural(extra, "record", "records")} PRISMA does not count`
    notes.push(
      "These are most likely results of a search that a broader retry replaced, but they cannot be matched to it, so they show as Not screened.",
    )
  }
  if (duplicates > 0) {
    notes.push(
      `The identified records include ${plural(duplicates, "duplicate", "duplicates")} removed before screening (PRISMA "duplicates removed").`,
    )
  }
  return [`${equation}.`, ...notes].join(" ")
}
