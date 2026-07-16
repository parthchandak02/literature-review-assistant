import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertTriangle, Download, FileCode, FileType, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { APIResponseError, downloadUrl, triggerExport } from "@/lib/api"
import {
  findFileByName,
  formatExportError,
  hasCompleteSubmission,
  hasPartialSubmission,
} from "./manuscriptUtils"

type ExportState = "idle" | "loading" | "done" | "error"

interface ManuscriptActionsProps {
  docxPath: string | null
  canExport: boolean
  exportRunId: string | null | undefined
  allOutputs: Record<string, unknown>
  onExportReadyChange?: (ready: boolean) => void
}

export function ManuscriptActions({
  docxPath,
  canExport,
  exportRunId,
  allOutputs,
  onExportReadyChange,
}: ManuscriptActionsProps) {
  const [exportState, setExportState] = useState<ExportState>("idle")
  const [exportFiles, setExportFiles] = useState<string[]>([])
  const [exportError, setExportError] = useState<string | null>(null)
  const [packagingIncomplete, setPackagingIncomplete] = useState(false)
  const prefix = exportRunId ?? "manuscript"

  const handleExport = useCallback(async (force = false) => {
    if (!exportRunId) return
    setExportError(null)
    setExportState("loading")
    try {
      const result = await triggerExport(exportRunId, force)
      setExportFiles(result.files)
      onExportReadyChange?.(result.files.length > 0)
      setExportState("done")
    } catch (error) {
      if (error instanceof APIResponseError && error.status === 409) {
        setPackagingIncomplete(true)
        setExportError(null)
        onExportReadyChange?.(false)
        setExportState("idle")
        return
      }
      setExportError(formatExportError(error))
      onExportReadyChange?.(false)
      setExportState("error")
    }
  }, [exportRunId, onExportReadyChange])

  const completeSubmission = useMemo(
    () => hasCompleteSubmission(allOutputs),
    [allOutputs],
  )
  const partialSubmission = useMemo(
    () => hasPartialSubmission(allOutputs),
    [allOutputs],
  )

  useEffect(() => {
    if (partialSubmission) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror partial submission into packaging banner
      setPackagingIncomplete(true)
    }
  }, [partialSubmission])

  // Reuse an already-packaged submission without re-running export.
  useEffect(() => {
    if (completeSubmission && exportState === "idle") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setExportState("done")
      onExportReadyChange?.(true)
    }
  }, [completeSubmission, exportState, onExportReadyChange])

  // Auto-trigger export once when the run is ready and packaging has not been attempted.
  // Skip when submission/ exists but is incomplete (a failed package leaves partial files
  // and would fail the same way on every mount until the user clicks Retry).
  useEffect(() => {
    if (canExport && exportState === "idle" && !completeSubmission && !partialSubmission) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void handleExport()
    }
  }, [canExport, completeSubmission, partialSubmission, exportState, handleExport])

  // After export, merge the generated file paths into the outputs map
  const mergedOutputs = useMemo<Record<string, unknown>>(() => {
    if (exportFiles.length === 0) return allOutputs
    const submission: Record<string, string> = {}
    for (const filePath of exportFiles) {
      const name = filePath.split("/").pop() ?? filePath
      submission[name] = filePath
    }
    return { ...allOutputs, submission }
  }, [allOutputs, exportFiles])

  // Prefer the freshly packaged submission/manuscript.tex over doc_manuscript.tex.
  // findFileByName() matches substrings so "doc_manuscript.tex" would always win because
  // it also contains "manuscript.tex". When exportFiles is populated, look for the exact
  // submission path first before falling back to the SSE artifact map.
  const texPath = useMemo(() => {
    if (exportFiles.length > 0) {
      const submissionTex = exportFiles.find(f => /\/manuscript\.tex$/.test(f))
      if (submissionTex) return submissionTex
    }
    return findFileByName(mergedOutputs, "manuscript.tex")
  }, [mergedOutputs, exportFiles])
  // DOCX: prefer the post-export path; fall back to any pre-existing artifact path from the run
  const mergedDocxPath = useMemo(
    () => findFileByName(mergedOutputs, ".docx") ?? docxPath,
    [mergedOutputs, docxPath],
  )

  const sharedCls = "h-7 gap-1 text-xs border-border text-muted hover:text-foreground hover:border-border"

  return (
    <div className="flex items-center gap-1.5">
      {/* Packaging spinner shown while auto-export is in flight */}
      {exportState === "loading" && (
        <span className="flex items-center gap-1 text-xs text-muted">
          <Spinner size="sm" />
          Packaging...
        </span>
      )}

      {exportState === "idle" && packagingIncomplete && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => void handleExport(true)}
          className={sharedCls}
          title="Build IEEE submission package (.tex, .docx, study PDFs)"
        >
          <Download className="h-3 w-3" />
          Package manuscript
        </Button>
      )}

      {/* Retry button on failure */}
      {exportState === "error" && (
        <Button
          size="sm"
          variant="outline"
          onClick={() => void handleExport()}
          className={sharedCls}
          title={exportError ?? "Retry manuscript packaging"}
        >
          <AlertTriangle className="h-3 w-3 text-intent-danger" />
          Retry export
        </Button>
      )}

      {/* Download buttons -- shown once export is done (or if artifacts were already present) */}
      {(exportState === "done" || mergedDocxPath) && (
        <>
          {texPath && (
            <Button size="sm" variant="outline" asChild className={sharedCls}>
              <a href={downloadUrl(texPath)} download={`${prefix}-manuscript.tex`}>
                <FileCode className="h-3 w-3" />
                .tex
              </a>
            </Button>
          )}
          {exportRunId && (
            <Button size="sm" variant="outline" asChild className={sharedCls}>
              <a href={`/api/run/${exportRunId}/manuscript.docx`}>
                <FileType className="h-3 w-3 text-intent-info" />
                DOCX
              </a>
            </Button>
          )}
          {exportState === "done" && (
            <Button
              size="sm"
              onClick={() => { setExportState("idle"); void handleExport(true); }}
              className="h-7 gap-1 text-xs bg-surface-2 hover:bg-surface-3 text-foreground hover:text-foreground border-0 shadow-none"
              title="Regenerate manuscript .tex and DOCX"
            >
              <RefreshCw className="h-3 w-3 text-intent-success" />
              Refresh
            </Button>
          )}
        </>
      )}
    </div>
  )
}
