import { useCallback, useEffect, useMemo, useState } from "react"
import { BookOpen } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ResultsBlock } from "@/components/ui/section"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { fetchGradeSof } from "@/lib/api"
import type { GradeSofResponse } from "@/lib/api"
import { cn } from "@/lib/utils"
import { gradeRowView } from "./gradeSof"

function Missing({ children = "Not reported" }: { children?: string }) {
  return <span className="text-muted/70 italic">{children}</span>
}

const RATIONALE_PREVIEW_CHARS = 110

function Rationale({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  if (text.length <= RATIONALE_PREVIEW_CHARS) return <span>{text}</span>
  return (
    <span className="flex flex-col items-start gap-0.5">
      <span className={cn(!open && "line-clamp-2")}>{text}</span>
      <Button
        type="button"
        variant="link"
        size="xs"
        className="h-auto px-0"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Show less" : "Show more"}
      </Button>
    </span>
  )
}

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

  const rows = useMemo(() => (data?.rows ?? []).map(gradeRowView), [data])

  return (
    <ResultsBlock icon={BookOpen} title="GRADE Summary Of Findings">
      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : error ? (
        <FetchError message={error} onRetry={() => void load()} />
      ) : rows.length === 0 ? (
        <EmptyState icon={BookOpen} heading="No GRADE outcomes available." className="py-8" />
      ) : (
        <div className="overflow-x-auto glass-table-shell">
          <table className="w-full min-w-[44rem] text-xs">
            <thead className="sticky top-0 bg-card">
              <tr className="border-b border-border text-muted">
                <th className="py-2 px-3 text-left font-medium">Outcome</th>
                <th className="py-2 pr-3 text-left font-medium">Evidence</th>
                <th className="py-2 pr-3 text-left font-medium">Certainty</th>
                <th className="py-2 pr-3 text-left font-medium">Downgraded for</th>
                <th className="py-2 pr-3 text-left font-medium">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-border last:border-0 align-top">
                  <td className="py-2 px-3 text-foreground">{row.outcome ?? <Missing>Unnamed outcome</Missing>}</td>
                  <td className="py-2 pr-3 text-muted whitespace-nowrap">{row.studies ?? <Missing />}</td>
                  <td className="py-2 pr-3">
                    {row.certainty ? (
                      <Badge variant={row.certaintyVariant} size="sm">
                        {row.certainty}
                      </Badge>
                    ) : (
                      <Missing />
                    )}
                  </td>
                  <td className="py-2 pr-3 text-muted">{row.downgradeNote}</td>
                  <td className="py-2 pr-3 text-muted max-w-[36ch]">
                    {row.rationale ? <Rationale text={row.rationale} /> : <Missing />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ResultsBlock>
  )
}
