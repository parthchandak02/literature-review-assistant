import { useCallback, useEffect, useState } from "react"
import { BookOpen } from "lucide-react"
import { CollapsibleSection } from "@/components/ui/section"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { fetchGradeSof } from "@/lib/api"
import type { GradeSofResponse } from "@/lib/api"

export function GradeSofCard({ runId }: { runId: string }) {
  const [data, setData] = useState<GradeSofResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const payload = await fetchGradeSof(runId)
      setData(payload)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <CollapsibleSection icon={BookOpen} title="GRADE Summary Of Findings" defaultOpen={false}>
      <div className="p-4">
        {loading ? (
          <Skeleton className="h-24 w-full" />
        ) : error ? (
          <FetchError message={error} onRetry={() => void load()} />
        ) : !data || data.rows.length === 0 ? (
          <EmptyState icon={BookOpen} heading="No GRADE outcomes available." className="py-10" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-muted">
                  <th className="py-2 pr-3 text-left font-medium">Outcome</th>
                  <th className="py-2 pr-3 text-left font-medium">Studies</th>
                  <th className="py-2 pr-3 text-left font-medium">Participants</th>
                  <th className="py-2 pr-3 text-left font-medium">Effect</th>
                  <th className="py-2 pr-3 text-left font-medium">Certainty</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.outcome} className="border-b border-border align-top">
                    <td className="py-2 pr-3 text-foreground">{row.outcome}</td>
                    <td className="py-2 pr-3 text-muted">{row.studies ?? "-"}</td>
                    <td className="py-2 pr-3 text-muted">{row.participants ?? "-"}</td>
                    <td className="py-2 pr-3 text-muted">{row.effect || "-"}</td>
                    <td className="py-2 pr-3">
                      <div className="text-foreground">{row.certainty || "-"}</div>
                      {row.reasons && row.reasons.length > 0 && <div className="mt-0.5 text-muted">{row.reasons.join(", ")}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </CollapsibleSection>
  )
}
