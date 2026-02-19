import { useState, useMemo } from "react"
import { FileText, Lock, Loader2, PackageCheck, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsPanel } from "@/components/ResultsPanel"
import { triggerExport } from "@/lib/api"

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
          <Button
            size="sm"
            variant={exportState === "done" ? "outline" : "default"}
            disabled={exportState === "loading" || exportState === "done"}
            onClick={() => void handleExport()}
            className="shrink-0 gap-1.5"
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
      )}

      <ResultsPanel outputs={mergedOutputs} />
    </div>
  )
}
