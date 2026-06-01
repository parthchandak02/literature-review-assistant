import { useState, useMemo, useEffect, useRef, useCallback } from "react"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import {
  FileText,
  Lock,
  AlertTriangle,
  BookOpen,
  FileType,
  FileCode,
  RefreshCw,
  Download,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/feedback"
import { CustomDiagramsCard } from "@/components/CustomDiagramsCard"
import { ManuscriptImage } from "@/components/ManuscriptImage"
import { ResultsPanel } from "@/components/ResultsPanel"
import { ReferencesView } from "@/views/ReferencesView"
import { collectCustomDiagramItems } from "@/lib/customDiagrams"
import { EvidenceNetworkViz } from "@/components/EvidenceNetworkViz"
import {
  APIResponseError,
  fetchGradeSof,
  fetchArtifactText,
  prosperoFormDocxUrl,
  prosperoFormMarkdownUrl,
  triggerExport,
  downloadUrl,
  submissionZipUrl,
} from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { CollapsibleSection } from "@/components/ui/section"
import { cn } from "@/lib/utils"
import type { GradeSofResponse } from "@/lib/api"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isFilePath(val: unknown): val is string {
  if (typeof val !== "string") return false
  const t = val.trim()
  return (
    t.startsWith("runs/") ||
    t.startsWith("data/") ||
    t.startsWith("./") ||
    t.startsWith("/")
  )
}

function hasSubmissionArtifacts(obj: unknown): boolean {
  if (typeof obj === "string" && isFilePath(obj)) {
    return /\/submission\//.test(obj)
  }
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const value of Object.values(obj as Record<string, unknown>)) {
      if (hasSubmissionArtifacts(value)) return true
    }
  }
  return false
}

/** Match only files under run submission/, not doc_manuscript.tex etc. */
function findSubmissionFile(outputs: Record<string, unknown>, basename: string): string | null {
  function walk(obj: unknown): string | null {
    if (typeof obj === "string" && isFilePath(obj)) {
      if (obj.includes("/submission/") && obj.split("/").pop() === basename) return obj
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const v of Object.values(obj as Record<string, unknown>)) {
        const found = walk(v)
        if (found) return found
      }
    }
    return null
  }
  return walk(outputs)
}

function hasCompleteSubmission(outputs: Record<string, unknown>): boolean {
  return Boolean(
    findSubmissionFile(outputs, "manuscript.tex")
    && findSubmissionFile(outputs, "manuscript.docx")
    && findSubmissionFile(outputs, "references.bib"),
  )
}

function hasPartialSubmission(outputs: Record<string, unknown>): boolean {
  return hasSubmissionArtifacts(outputs) && !hasCompleteSubmission(outputs)
}

function findFileByName(outputs: Record<string, unknown>, namePart: string): string | null {
  function walk(obj: unknown): string | null {
    if (typeof obj === "string" && isFilePath(obj)) {
      const name = obj.split("/").pop() ?? ""
      if (name.toLowerCase().includes(namePart.toLowerCase())) return obj
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const v of Object.values(obj as Record<string, unknown>)) {
        const found = walk(v)
        if (found) return found
      }
    }
    return null
  }
  return walk(outputs)
}

function findAllFilesByExt(outputs: Record<string, unknown>, exts: string[]): string[] {
  const results: string[] = []
  function walk(obj: unknown) {
    if (typeof obj === "string" && isFilePath(obj)) {
      const name = (obj.split("/").pop() ?? "").toLowerCase()
      if (exts.some((ext) => name.endsWith(ext))) results.push(obj)
    } else if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const v of Object.values(obj as Record<string, unknown>)) walk(v)
    }
  }
  walk(outputs)
  return results
}

function makeUrlTransform(markdownFilePath: string) {
  return (url: string, key: string): string | undefined => {
    if (key === "src" && !/^(https?:\/\/|data:|\/)/i.test(url)) {
      const dir = markdownFilePath.split("/").slice(0, -1).join("/")
      const resolved = dir ? `${dir}/${url}` : url
      return downloadUrl(resolved)
    }
    return defaultUrlTransform(url)
  }
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
}

function extractHeadings(markdown: string): { level: number; text: string; slug: string }[] {
  const headings: { level: number; text: string; slug: string }[] = []
  const re = /^(#{1,3})\s+(.+)$/gm
  let match
  while ((match = re.exec(markdown)) !== null) {
    const text = match[2].trim()
    headings.push({ level: match[1].length, text, slug: slugify(text) })
  }
  return headings
}

function formatExportError(error: unknown): string {
  const stripExportLabel = (message: string) =>
    message.replace(/^Export failed:\s*/i, "").trim()

  if (error instanceof APIResponseError) {
    if (
      error.detail &&
      typeof error.detail === "object" &&
      "violations" in error.detail &&
      Array.isArray((error.detail as { violations?: unknown[] }).violations)
    ) {
      const violations = (error.detail as { violations: Array<{ code?: string }> }).violations
      const firstCode = violations[0]?.code
      if (firstCode) {
        return `${stripExportLabel(error.message)} (${firstCode}${violations.length > 1 ? ` +${violations.length - 1} more` : ""})`
      }
      return `${stripExportLabel(error.message)} (${violations.length} contract violation${violations.length === 1 ? "" : "s"})`
    }
    return stripExportLabel(error.message)
  }
  if (error instanceof Error) return stripExportLabel(error.message)
  return "Export failed"
}

// ---------------------------------------------------------------------------
// Manuscript inline viewer
// ---------------------------------------------------------------------------

function ManuscriptViewer({ filePath }: { filePath: string }) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [zoom, setZoom] = useState(100)
  const [showOutline, setShowOutline] = useState(false)
  const viewerRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    try {
      const text = await fetchArtifactText(filePath, signal)
      if (!signal?.aborted) setContent(text)
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [filePath])

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const headings = useMemo(() => content ? extractHeadings(content) : [], [content])

  function jumpTo(slug: string) {
    const container = viewerRef.current
    if (!container) return
    const target = container.querySelector(`#${CSS.escape(slug)}`) as HTMLElement | null
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  if (loading) {
    return (
      <div className="overflow-hidden">
        <div className="px-6 py-4 border-b border-border flex items-center gap-2">
          <Spinner size="sm" />
          <span className="text-sm text-muted">Loading manuscript...</span>
        </div>
        <div className="p-6 space-y-4">
          <Skeleton className="h-7 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-6 w-1/2 mt-6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </div>
    )
  }

  if (error) {
    return <FetchError message={`Could not load manuscript: ${error}`} onRetry={() => void load()} />
  }

  if (!content) return null

  return (
    <div className="overflow-hidden">
      {/* Toolbar: outline toggle + zoom control */}
      <div className="glass-toolbar flex items-center justify-between px-4 h-9 border-b border-border/70 shrink-0">
        {/* Outline toggle */}
        <button
          onClick={() => setShowOutline((v) => !v)}
          className={cn(
            "flex items-center gap-1.5 text-xs rounded px-1.5 py-1 transition-colors",
            showOutline
              ? "text-foreground bg-surface-2/60 hover:bg-surface-2"
              : "text-muted hover:text-foreground hover:bg-surface-2/40",
          )}
          title={showOutline ? "Hide outline" : "Show outline"}
        >
          <BookOpen className="h-3.5 w-3.5" />
          Outline
        </button>

        {/* Zoom control */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setZoom((z) => Math.max(70, z - 15))}
            disabled={zoom <= 70}
            className="w-6 h-6 rounded text-sm font-mono text-muted hover:text-foreground hover:bg-surface-2 disabled:opacity-30 transition-colors"
          >
            -
          </button>
          <span className="text-xs font-mono text-muted w-10 text-center tabular-nums">{zoom}%</span>
          <button
            onClick={() => setZoom((z) => Math.min(160, z + 15))}
            disabled={zoom >= 160}
            className="w-6 h-6 rounded text-sm font-mono text-muted hover:text-foreground hover:bg-surface-2 disabled:opacity-30 transition-colors"
          >
            +
          </button>
        </div>
      </div>

      {/* Vertical outline panel -- collapsible */}
      {showOutline && headings.length > 0 && (
        <div className="glass-toolbar border-b border-border/70 max-h-52 overflow-y-auto">
          <nav className="py-1">
            {headings.map((h) => (
              <button
                key={h.slug}
                onClick={() => jumpTo(h.slug)}
                className={cn(
                  "w-full text-left px-4 py-1 text-xs transition-colors hover:bg-surface-2/50 truncate block",
                  h.level === 1
                    ? "text-foreground font-semibold pl-4"
                    : h.level === 2
                    ? "text-muted pl-7"
                    : "text-muted pl-10",
                )}
              >
                {h.text}
              </button>
            ))}
          </nav>
        </div>
      )}

      {/* Manuscript body */}
      <div ref={viewerRef} className="overflow-auto max-h-[70vh] p-6 md:p-10">
        <div className="prose prose-zinc max-w-3xl mx-auto manuscript-viewer" style={{ fontSize: `${zoom}%` }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[
              rehypeSlug,
              [rehypeAutolinkHeadings, { behavior: "wrap" }],
              rehypeHighlight,
            ]}
            urlTransform={makeUrlTransform(filePath)}
            components={{
              img: ManuscriptImage,
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Evidence Network collapsible section
// ---------------------------------------------------------------------------

function EvidenceNetworkSection({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  return (
    <CollapsibleSection
      title="Evidence Network"
      open={open}
      onToggle={() => setOpen((v) => !v)}
    >
      <div className="p-4">
        {open && <EvidenceNetworkViz runId={runId} />}
      </div>
    </CollapsibleSection>
  )
}

function GradeSofCard({ runId }: { runId: string }) {
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

function ProsperoDownloadsCard({ runId }: { runId: string }) {
  return (
    <CollapsibleSection icon={Download} title="PROSPERO Draft" defaultOpen={false}>
      <div className="p-4 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" asChild className="h-8 gap-1 text-xs border-border text-foreground">
          <a href={prosperoFormDocxUrl(runId)}>
            <FileType className="h-3 w-3 text-intent-info" />
            PROSPERO DOCX
          </a>
        </Button>
        <Button size="sm" variant="outline" asChild className="h-8 gap-1 text-xs border-border text-foreground">
          <a href={prosperoFormMarkdownUrl(runId)}>
            <FileCode className="h-3 w-3 text-intent-success" />
            PROSPERO Markdown
          </a>
        </Button>
        </div>
    </CollapsibleSection>
  )
}

function PrismaDiagramCard({ filePath }: { filePath: string }) {
  return (
    <CollapsibleSection icon={FileText} title="PRISMA Diagram" defaultOpen={false}>
      <div className="p-4">
        <div className="rounded-xl border border-border bg-card p-2">
          <img src={downloadUrl(filePath)} alt="PRISMA flow diagram" className="w-full h-auto rounded-lg" />
        </div>
      </div>
    </CollapsibleSection>
  )
}

// ---------------------------------------------------------------------------
// Manuscript section header actions
// ---------------------------------------------------------------------------

type ExportState = "idle" | "loading" | "done" | "error"

interface ManuscriptActionsProps {
  docxPath: string | null
  canExport: boolean
  exportRunId: string | null | undefined
  allOutputs: Record<string, unknown>
  onExportReadyChange?: (ready: boolean) => void
}

function ManuscriptActions({
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

interface ResultsViewProps {
  outputs: Record<string, unknown>
  isDone: boolean
  runId: string
  workflowId: string | null
  historyOutputs?: Record<string, string>
  exportRunId?: string | null
  onGoToSubmissionReferencePapers?: () => void
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
}

export function ResultsView({
  outputs,
  isDone,
  runId,
  workflowId,
  historyOutputs = {},
  exportRunId,
  onGoToSubmissionReferencePapers,
  submissionFocusTarget = null,
  submissionFocusToken = 0,
}: ResultsViewProps) {
  const effectiveOutputs = useMemo<Record<string, unknown>>(() => {
    const base =
      Object.keys(outputs).length > 0
        ? outputs
        : Object.keys(historyOutputs).length > 0
          ? { artifacts: historyOutputs }
          : {}
    if (exportRunId && Object.keys(base).length > 0) {
      return {
        ...base,
        submission_zip: submissionZipUrl(exportRunId),
      }
    }
    return base
  }, [outputs, historyOutputs, exportRunId])

  const isHistorical = !isDone && Object.keys(historyOutputs).length > 0
  const hasResults = isDone || isHistorical
  const canExport = exportRunId != null && hasResults
  const [artifactsOpen, setArtifactsOpen] = useState(false)
  const [referencesOpen, setReferencesOpen] = useState(false)
  const [submissionReady, setSubmissionReady] = useState(false)

  const manuscriptPath = useMemo(
    () => findFileByName(effectiveOutputs, "doc_manuscript"),
    [effectiveOutputs],
  )

  const docxPath = useMemo(
    () => findFileByName(effectiveOutputs, ".docx"),
    [effectiveOutputs],
  )

  const prismaDiagramPath = useMemo(() => {
    const imagePaths = findAllFilesByExt(effectiveOutputs, [".png", ".svg", ".jpg", ".jpeg", ".webp"])
    const customPaths = new Set(collectCustomDiagramItems(effectiveOutputs).map((d) => d.path))
    return (
      imagePaths.find((path) => /prisma|flow/i.test(path) && !customPaths.has(path)) ?? null
    )
  }, [effectiveOutputs])

  const customDiagramPaths = useMemo(
    () => collectCustomDiagramItems(effectiveOutputs).map((d) => d.path),
    [effectiveOutputs],
  )

  // Paths to exclude from Artifacts panel (they live in the left panel header actions)
  const manuscriptExcludePaths = useMemo<Set<string>>(() => {
    const paths = new Set<string>()
    if (manuscriptPath) paths.add(manuscriptPath)
    if (docxPath) paths.add(docxPath)
    const texFiles = findAllFilesByExt(effectiveOutputs, [".tex"])
    texFiles.forEach((p) => paths.add(p))
    customDiagramPaths.forEach((p) => paths.add(p))
    if (prismaDiagramPath) paths.add(prismaDiagramPath)
    return paths
  }, [effectiveOutputs, manuscriptPath, docxPath, customDiagramPaths, prismaDiagramPath])

  useEffect(() => {
    setSubmissionReady(hasSubmissionArtifacts(effectiveOutputs))
  }, [effectiveOutputs])

  useEffect(() => {
    if (submissionFocusTarget && !artifactsOpen) {
      setArtifactsOpen(true)
    }
  }, [submissionFocusTarget, submissionFocusToken, artifactsOpen])

  if (!hasResults) {
    return (
      <EmptyState
        icon={Lock}
        heading="Results available once the review completes."
        sub="Switch to the Activity tab to monitor progress."
        className="h-64"
      />
    )
  }

  if (Object.keys(effectiveOutputs).length === 0) {
    return (
      <EmptyState
        icon={FileText}
        heading="No output files found."
        className="h-64"
      />
    )
  }

  return (
    <div className="flex flex-col gap-3 min-h-[520px]">
      {manuscriptPath && (
        <CollapsibleSection
          icon={FileText}
          title="Manuscript"
          defaultOpen={false}
          actions={
            <ManuscriptActions
              docxPath={docxPath}
              canExport={canExport}
              exportRunId={exportRunId}
              allOutputs={effectiveOutputs}
              onExportReadyChange={setSubmissionReady}
            />
          }
        >
          <ManuscriptViewer filePath={manuscriptPath} />
        </CollapsibleSection>
      )}

      <CollapsibleSection
        icon={FileText}
        title="Artifacts"
        description="Protocol, data files, figures, quality summaries"
        open={artifactsOpen}
        onToggle={() => setArtifactsOpen((v) => !v)}
        actions={
          exportRunId ? (
            submissionReady ? (
              <Button
                size="sm"
                asChild
                className="h-7 gap-1 text-xs bg-intent-success hover:bg-intent-success text-intent-success-fg border-0 shadow-none"
              >
                <a href={submissionZipUrl(exportRunId)} download>
                  <Download className="h-3 w-3" />
                  Submission Package
                </a>
              </Button>
            ) : (
              <Button
                size="sm"
                disabled
                className="h-7 gap-1 text-xs bg-surface-2 text-muted border-0 shadow-none cursor-not-allowed"
                title="Run manuscript export first"
              >
                <Download className="h-3 w-3" />
                Submission Package
              </Button>
            )
          ) : null
        }
      >
        <div className="p-4 space-y-3">
          {prismaDiagramPath ? <PrismaDiagramCard filePath={prismaDiagramPath} /> : null}

          <CustomDiagramsCard outputs={effectiveOutputs} />

          {exportRunId ? <GradeSofCard runId={exportRunId} /> : null}

          {exportRunId ? <ProsperoDownloadsCard runId={exportRunId} /> : null}

          {exportRunId ? <EvidenceNetworkSection runId={exportRunId} /> : null}

          <ResultsPanel
            outputs={effectiveOutputs}
            excludePaths={manuscriptExcludePaths}
            runId={exportRunId}
            submissionFocusTarget={submissionFocusTarget}
            submissionFocusToken={submissionFocusToken}
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        icon={BookOpen}
        title="References"
        description="Included studies and source files"
        open={referencesOpen}
        onToggle={() => setReferencesOpen((v) => !v)}
      >
        <div className="p-4">
          <ReferencesView
            runId={runId}
            workflowId={workflowId}
            isDone={isDone}
            onGoToSubmissionReferencePapers={onGoToSubmissionReferencePapers}
          />
        </div>
      </CollapsibleSection>
    </div>
  )
}
