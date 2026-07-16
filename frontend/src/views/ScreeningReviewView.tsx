import { useState, useEffect, useCallback } from "react"
import { Spinner, FetchError } from "@/components/ui/feedback"
import { ScreeningApprovalBar } from "@/components/screening/ScreeningApprovalBar"
import { ScreeningFiltersBar, type ScreeningFilter } from "@/components/screening/ScreeningFiltersBar"
import { ScreeningPaperList } from "@/components/screening/ScreeningPaperList"
import { ScreeningStatsBar } from "@/components/screening/ScreeningStatsBar"
import { ScreeningSummaryHeader } from "@/components/screening/ScreeningSummaryHeader"
import { fetchScreeningSummary, approveScreening } from "@/lib/api"
import type { ScreeningSummary, ScreeningOverride } from "@/lib/api"

export function ScreeningReviewView({ runId }: { runId: string }) {
  const [summary, setSummary] = useState<ScreeningSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [approving, setApproving] = useState(false)
  const [approved, setApproved] = useState(false)
  const [filter, setFilter] = useState<ScreeningFilter>("all")
  const [overrides, setOverrides] = useState<Map<string, ScreeningOverride>>(new Map())

  const load = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await fetchScreeningSummary(runId)
      setSummary(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    setOverrides(new Map())
    void load()
  }, [load])

  const handleOverride = (paperId: string, override: ScreeningOverride | null) => {
    setOverrides((prev) => {
      const next = new Map(prev)
      if (override === null) {
        next.delete(paperId)
      } else {
        next.set(paperId, override)
      }
      return next
    })
  }

  const handleApprove = async () => {
    if (approving || approved) return
    setApproving(true)
    try {
      const overrideList = Array.from(overrides.values())
      await approveScreening(runId, overrideList.length > 0 ? overrideList : undefined)
      setApproved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setApproving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <Spinner size="md" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-8">
        <FetchError message={error} onRetry={() => void load()} />
      </div>
    )
  }

  if (!summary) return null

  const filtered = summary.papers.filter(
    (p) => filter === "all" || p.decision === filter,
  )

  const includedCount = summary.papers.filter((p) => p.decision === "include").length
  const uncertainCount = summary.papers.filter((p) => p.decision === "uncertain").length

  return (
    <div className="space-y-5">
      <ScreeningSummaryHeader />

      <ScreeningStatsBar
        total={summary.total}
        includedCount={includedCount}
        uncertainCount={uncertainCount}
      />

      <ScreeningApprovalBar
        approved={approved}
        approving={approving}
        overrideCount={overrides.size}
        onApprove={() => void handleApprove()}
      />

      <ScreeningFiltersBar
        filter={filter}
        total={summary.total}
        includedCount={includedCount}
        uncertainCount={uncertainCount}
        onFilterChange={setFilter}
      />

      <ScreeningPaperList
        papers={filtered}
        overrides={overrides}
        onOverride={handleOverride}
      />
    </div>
  )
}
