import { useState, useMemo, useEffect } from "react"
import { FileText, Lock, Loader2, PackageCheck, AlertCircle, ChevronDown, ChevronUp, CheckCircle, XCircle, AlertTriangle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsPanel } from "@/components/ResultsPanel"
import { triggerExport } from "@/lib/api"
import { cn } from "@/lib/utils"


interface ResultsViewProps {
  outputs: Record<string, unknown>
  isDone: boolean
  historyOutputs?: Record<string, string>
  exportRunId?: string | null
}

type ExportState = "idle" | "loading" | "done" | "error"

export function ResultsView({
  outputs,
  isDone,
  historyOutputs = {},
  exportRunId,
}: ResultsViewProps) {
  const [exportState, setExportState] = useState<ExportState>("idle")
  const [exportError, setExportError] = useState<string | null>(null)
  const [exportFiles, setExportFiles] = useState<string[]>([])

  // Derive the effective outputs to show.
  // For live completed runs: the full run_summary dict (artifacts nested inside).
  // For historical runs: wrap historyOutputs under "artifacts" so ResultsPanel's
  // recursive walker finds the paths the same way it does for live runs.
  const effectiveOutputs = useMemo<Record<string, unknown>>(() => {
    if (Object.keys(outputs).length > 0) return outputs
    if (Object.keys(historyOutputs).length > 0) return { artifacts: historyOutputs }
    return {}
  }, [outputs, historyOutputs])

  // Inject export files into the outputs dict so ResultsPanel renders them.
  const mergedOutputs = useMemo<Record<string, unknown>>(() => {
    if (exportFiles.length === 0) return effectiveOutputs
    const submission: Record<string, string> = {}
    for (const filePath of exportFiles) {
      const name = filePath.split("/").pop() ?? filePath
      submission[name] = filePath
    }
    return { ...effectiveOutputs, submission }
  }, [effectiveOutputs, exportFiles])

  const isHistorical = !isDone && Object.keys(historyOutputs).length > 0
  const hasResults = isDone || isHistorical
  const canExport = exportRunId != null && hasResults

  async function handleExport() {
    if (!exportRunId) return
    setExportState("loading")
    setExportError(null)
    try {
      const result = await triggerExport(exportRunId)
      setExportFiles(result.files)
      setExportState("done")
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Export failed")
      setExportState("error")
    }
  }

  if (!hasResults) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
        <Lock className="h-10 w-10 text-zinc-700" />
        <p className="text-zinc-500 text-sm">Results will be available once the review completes.</p>
      </div>
    )
  }

  if (Object.keys(mergedOutputs).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
        <FileText className="h-10 w-10 text-zinc-700" />
        <p className="text-zinc-500 text-sm">No output files found.</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl flex flex-col gap-4">
      {/* Export to LaTeX action bar */}
      {canExport && (
        <div className="flex items-center justify-between gap-4 bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-zinc-200">IEEE LaTeX Export</span>
            <span className="text-xs text-zinc-500">
              {exportState === "done"
                ? "Submission package ready. Files listed below."
                : "Package manuscript.tex, references.bib, and figures for submission."}
            </span>
            {exportState === "error" && exportError && (
              <span className="text-xs text-red-400 flex items-center gap-1 mt-0.5">
                <AlertCircle className="h-3 w-3" />
                {exportError}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              size="sm"
              variant={exportState === "done" ? "outline" : "default"}
              disabled={exportState === "loading" || exportState === "done"}
              onClick={() => void handleExport()}
              className="gap-1.5"
            >
              {exportState === "loading" ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Packaging...
                </>
              ) : exportState === "done" ? (
                <>
                  <PackageCheck className="h-3.5 w-3.5" />
                  Exported
                </>
              ) : (
                "Export to LaTeX"
              )}
            </Button>
          </div>
        </div>
      )}

      {exportRunId && <PrismaChecklistPanel runId={exportRunId} />}

      <ResultsPanel outputs={mergedOutputs} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// PRISMA 2020 Compliance Panel
// ---------------------------------------------------------------------------

interface PrismaItem {
  item_id: string
  section: string
  description: string
  status: "REPORTED" | "PARTIAL" | "MISSING"
  rationale: string
}

interface PrismaChecklist {
  run_id: string
  reported_count: number
  partial_count: number
  missing_count: number
  passed: boolean
  total: number
  items: PrismaItem[]
}

function PrismaStatusIcon({ status }: { status: string }) {
  if (status === "REPORTED") return <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
  if (status === "PARTIAL") return <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
  return <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
}

function PrismaChecklistPanel({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<PrismaChecklist | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sectionFilter, setSectionFilter] = useState<string>("All")

  useEffect(() => {
    if (!open || data) return
    setLoading(true)
    setError(null)
    const apiBase = import.meta.env.VITE_API_URL ?? ""
    fetch(`${apiBase}/api/run/${runId}/prisma-checklist`)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}`)
        return res.json() as Promise<PrismaChecklist>
      })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [open, runId, data])

  const sections = data
    ? ["All", ...Array.from(new Set(data.items.map((i) => i.section)))]
    : ["All"]

  const filtered = data
    ? sectionFilter === "All"
      ? data.items
      : data.items.filter((i) => i.section === sectionFilter)
    : []

  const passColor = data?.passed ? "text-emerald-400" : "text-amber-400"

  return (
    <div className="border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900/40">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-zinc-500" />
          <span className="text-sm font-medium text-zinc-200">PRISMA 2020 Compliance</span>
          {data && (
            <span className={cn("text-xs font-mono font-semibold", passColor)}>
              {data.reported_count}/{data.total}
              {data.passed ? " -- PASS" : " -- needs attention"}
            </span>
          )}
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-zinc-600" />
        ) : (
          <ChevronDown className="h-4 w-4 text-zinc-600" />
        )}
      </button>

      {open && (
        <div className="border-t border-zinc-800 p-4 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking manuscript...
            </div>
          )}
          {error && (
            <p className="text-sm text-red-400">Failed to load checklist: {error}</p>
          )}
          {data && (
            <>
              {/* Summary bar */}
              <div className="flex items-center gap-4 text-xs flex-wrap">
                <span className="text-emerald-400 font-semibold">{data.reported_count} Reported</span>
                <span className="text-amber-400 font-semibold">{data.partial_count} Partial</span>
                <span className="text-red-400 font-semibold">{data.missing_count} Missing</span>
                <span className={cn("font-semibold ml-auto", passColor)}>
                  {data.passed ? "PASS (>=24 reported)" : "FAIL (<24 reported)"}
                </span>
              </div>

              {/* Section filter */}
              <div className="flex items-center gap-1 flex-wrap">
                {sections.map((s) => (
                  <button
                    key={s}
                    onClick={() => setSectionFilter(s)}
                    className={cn(
                      "px-2.5 py-1 rounded-full text-xs border transition-colors",
                      sectionFilter === s
                        ? "border-violet-600 bg-violet-900/40 text-violet-300"
                        : "border-zinc-700 text-zinc-500 hover:text-zinc-300",
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>

              {/* Item list */}
              <div className="space-y-1">
                {filtered.map((item) => (
                  <div
                    key={item.item_id}
                    className={cn(
                      "flex items-start gap-2.5 px-3 py-2 rounded-lg text-xs",
                      item.status === "REPORTED"
                        ? "bg-emerald-900/10"
                        : item.status === "PARTIAL"
                          ? "bg-amber-900/10"
                          : "bg-red-900/10",
                    )}
                  >
                    <PrismaStatusIcon status={item.status} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-zinc-500">{item.item_id}</span>
                        <span className="text-zinc-400 font-medium">{item.description}</span>
                        <span className="text-zinc-600 ml-auto">{item.section}</span>
                      </div>
                      {item.rationale && (
                        <p className="text-zinc-600 mt-0.5">{item.rationale}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
