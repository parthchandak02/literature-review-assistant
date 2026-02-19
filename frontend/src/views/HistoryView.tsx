import { useCallback, useEffect, useState } from "react"
import { fetchHistory } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import { cn } from "@/lib/utils"
import { AlertTriangle, Clock, Database, Loader, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

const STATUS_STYLE: Record<string, string> = {
  completed: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  running: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  error: "text-red-400 bg-red-500/10 border-red-500/20",
  failed: "text-red-400 bg-red-500/10 border-red-500/20",
  interrupted: "text-zinc-400 bg-zinc-800/60 border-zinc-700",
}

function formatDate(raw: string): string {
  if (!raw) return "--"
  try {
    const d = new Date(raw.includes("T") ? raw : raw.replace(" ", "T") + "Z")
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return raw.slice(0, 16)
  }
}

/** True if a run has a db_path that could be browsed (including partial/stale runs). */
function canOpen(entry: HistoryEntry): boolean {
  return Boolean(entry.db_path)
}

/** True if a run may be stale (was marked running but backend has likely restarted). */
function isLikelyStale(entry: HistoryEntry): boolean {
  return entry.status.toLowerCase() === "running"
}

interface HistoryViewProps {
  onAttach: (entry: HistoryEntry) => Promise<void>
}

export function HistoryView({ onAttach }: HistoryViewProps) {
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [openErrors, setOpenErrors] = useState<Record<string, string>>({})
  const [fetchError, setFetchError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const data = await fetchHistory()
      setEntries(data)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setFetchError(
        msg.toLowerCase().includes("failed to fetch") || msg.toLowerCase().includes("load failed")
          ? "Cannot reach backend. Start the server and refresh."
          : msg,
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleOpen(entry: HistoryEntry) {
    setOpeningId(entry.workflow_id)
    setOpenErrors((prev) => {
      const next = { ...prev }
      delete next[entry.workflow_id]
      return next
    })
    try {
      await onAttach(entry)
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setOpenErrors((prev) => ({ ...prev, [entry.workflow_id]: msg }))
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="max-w-4xl flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-zinc-200">Past Reviews</h2>
          <p className="text-xs text-zinc-500 mt-1">
            All reviews recorded on this machine.
            Click "Open" to explore a run's database and results.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={load}
          disabled={loading}
          className="border-zinc-700 text-zinc-400 hover:text-zinc-200 gap-1.5 h-8"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Fetch error */}
      {fetchError && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5">
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>{fetchError}</span>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && entries.length === 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex gap-3 items-center">
              <div className="h-4 bg-zinc-800 rounded animate-pulse flex-1" />
              <div className="h-4 bg-zinc-800 rounded animate-pulse w-20" />
              <div className="h-4 bg-zinc-800 rounded animate-pulse w-32" />
              <div className="h-7 bg-zinc-800 rounded animate-pulse w-16" />
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && entries.length === 0 && !fetchError && (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-center bg-zinc-900 border border-zinc-800 rounded-xl">
          <Clock className="h-10 w-10 text-zinc-700" />
          <p className="text-zinc-400 text-sm font-medium">No past reviews found</p>
          <p className="text-zinc-600 text-xs max-w-xs leading-relaxed">
            Run your first systematic review using "New Review".
            Completed runs will appear here automatically.
          </p>
        </div>
      )}

      {/* Table */}
      {entries.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="text-left px-5 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wide">
                  Research Question
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wide">
                  Status
                </th>
                <th className="text-left px-4 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wide">
                  Date
                </th>
                <th className="px-5 py-3 text-xs font-medium text-zinc-500 uppercase tracking-wide text-right">
                  Open
                </th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, i) => {
                const statusKey = entry.status.toLowerCase()
                const statusStyle =
                  STATUS_STYLE[statusKey] ?? "text-zinc-400 bg-zinc-800/60 border-zinc-700"
                const isOpening = openingId === entry.workflow_id
                const openError = openErrors[entry.workflow_id]
                const stale = isLikelyStale(entry)
                const openable = canOpen(entry)

                return (
                  <tr
                    key={entry.workflow_id}
                    className={cn(
                      "border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors",
                      i === entries.length - 1 && "border-0",
                    )}
                  >
                    {/* Topic */}
                    <td className="px-5 py-3.5 max-w-xs">
                      <span className="text-zinc-200 text-sm line-clamp-2 leading-snug">
                        {entry.topic}
                      </span>
                      <span className="text-zinc-600 text-[10px] font-mono block mt-0.5">
                        {entry.workflow_id}
                      </span>
                    </td>

                    {/* Status badge */}
                    <td className="px-4 py-3.5">
                      <div className="flex flex-col gap-1">
                        <span
                          className={cn(
                            "inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border w-fit",
                            statusStyle,
                          )}
                        >
                          {entry.status}
                        </span>
                        {stale && (
                          <span className="text-[10px] text-amber-500/70 flex items-center gap-1">
                            <AlertTriangle className="h-2.5 w-2.5" />
                            may be incomplete
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Date */}
                    <td className="px-4 py-3.5 text-xs text-zinc-500 whitespace-nowrap">
                      {formatDate(entry.created_at)}
                    </td>

                    {/* Open button */}
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex flex-col items-end gap-1">
                        {openable ? (
                          <Button
                            size="sm"
                            onClick={() => handleOpen(entry)}
                            disabled={isOpening}
                            className="h-7 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 gap-1.5"
                            variant="outline"
                          >
                            {isOpening ? (
                              <Loader className="h-3 w-3 animate-spin" />
                            ) : (
                              <Database className="h-3 w-3" />
                            )}
                            {isOpening ? "Opening..." : "Open"}
                          </Button>
                        ) : (
                          <span className="text-zinc-700 text-xs">Unavailable</span>
                        )}
                        {openError && (
                          <span className="text-[10px] text-red-400 max-w-[140px] text-right leading-tight">
                            {openError}
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Footer hint */}
      {entries.length > 0 && (
        <p className="text-xs text-zinc-700 text-center">
          {entries.length} run{entries.length !== 1 ? "s" : ""} found in logs/workflows_registry.db
        </p>
      )}
    </div>
  )
}
