import { useState, useMemo, useEffect, useRef, useCallback } from "react"
import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import {
  FileText,
  Lock,
  Loader2,
  CheckCircle,
  XCircle,
  AlertTriangle,
  BookOpen,
  FileType,
  FileCode,
  RefreshCw,
  Download,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsPanel } from "@/components/ResultsPanel"
import { EvidenceNetworkViz } from "@/components/EvidenceNetworkViz"
import {
  APIResponseError,
  triggerExport,
  fetchPrismaChecklist,
  downloadUrl,
  submissionZipUrl,
} from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError, EmptyState } from "@/components/ui/feedback"
import { CollapsibleSection } from "@/components/ui/section"
import { cn } from "@/lib/utils"
import type { PrismaChecklist } from "@/lib/api"

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
        return `${error.message} (${firstCode}${violations.length > 1 ? ` +${violations.length - 1} more` : ""})`
      }
      return `${error.message} (${violations.length} contract violation${violations.length === 1 ? "" : "s"})`
    }
    return error.message
  }
  if (error instanceof Error) return error.message
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

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(downloadUrl(filePath))
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setContent(await res.text())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [filePath])

  useEffect(() => {
    void load()
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
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-violet-400" />
          <span className="text-sm text-zinc-400">Loading manuscript...</span>
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
      <div className="glass-toolbar flex items-center justify-between px-4 h-9 border-b border-zinc-800/70 shrink-0">
        {/* Outline toggle */}
        <button
          onClick={() => setShowOutline((v) => !v)}
          className={cn(
            "flex items-center gap-1.5 text-xs rounded px-1.5 py-1 transition-colors",
            showOutline
              ? "text-zinc-300 bg-zinc-800/60 hover:bg-zinc-800"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40",
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
            className="w-6 h-6 rounded text-sm font-mono text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 transition-colors"
          >
            -
          </button>
          <span className="text-xs font-mono text-zinc-400 w-10 text-center tabular-nums">{zoom}%</span>
          <button
            onClick={() => setZoom((z) => Math.min(160, z + 15))}
            disabled={zoom >= 160}
            className="w-6 h-6 rounded text-sm font-mono text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 disabled:opacity-30 transition-colors"
          >
            +
          </button>
        </div>
      </div>

      {/* Vertical outline panel -- collapsible */}
      {showOutline && headings.length > 0 && (
        <div className="glass-toolbar border-b border-zinc-800/70 max-h-52 overflow-y-auto">
          <nav className="py-1">
            {headings.map((h) => (
              <button
                key={h.slug}
                onClick={() => jumpTo(h.slug)}
                className={cn(
                  "w-full text-left px-4 py-1 text-xs transition-colors hover:bg-zinc-800/50 truncate block",
                  h.level === 1
                    ? "text-zinc-300 font-semibold pl-4"
                    : h.level === 2
                    ? "text-zinc-400 pl-7"
                    : "text-zinc-500 pl-10",
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
        <div className="prose prose-invert prose-zinc max-w-3xl mx-auto" style={{ fontSize: `${zoom}%` }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[
              rehypeSlug,
              [rehypeAutolinkHeadings, { behavior: "wrap" }],
              rehypeHighlight,
            ]}
            urlTransform={makeUrlTransform(filePath)}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PRISMA inline collapsible card
// ---------------------------------------------------------------------------

function PrismaStatusIcon({ status }: { status: string }) {
  if (status === "REPORTED") return <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
  if (status === "PARTIAL") return <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
  if (status === "NOT_APPLICABLE") return <BookOpen className="h-3.5 w-3.5 text-zinc-500 shrink-0" />
  return <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
}

function PrismaCard({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<PrismaChecklist | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sectionFilter, setSectionFilter] = useState<string>("All")
  const hasFetched = useRef(false)
  const fetchChecklist = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchPrismaChecklist(runId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    // Reset sticky fetch state when user switches runs.
    hasFetched.current = false
    setData(null)
    setError(null)
    setSectionFilter("All")
  }, [runId])

  function handleToggle() {
    setOpen((v) => !v)
    if (!hasFetched.current) {
      hasFetched.current = true
      void fetchChecklist()
    }
  }

  const sections = data
    ? ["All", ...Array.from(new Set(data.items.map((i) => i.section)))]
    : ["All"]

  const filtered = data
    ? sectionFilter === "All"
      ? data.items
      : data.items.filter((i) => i.section === sectionFilter)
    : []

  const scoreChip = data && data.total > 0 ? (
    <span className={cn(
      "text-[10px] font-mono px-1.5 py-0.5 rounded border shrink-0",
      data.passed
        ? "text-emerald-400 border-emerald-800 bg-emerald-900/20"
        : "text-amber-400 border-amber-800 bg-amber-900/20",
    )}>
      {data.reported_count}/{data.total} {data.passed ? "PASS" : "review"}
    </span>
  ) : null

  return (
    <CollapsibleSection
      icon={CheckCircle}
      title="PRISMA 2020 Compliance"
      badge={scoreChip}
      open={open}
      onToggle={handleToggle}
    >
      <div className="p-4 space-y-4">
          {loading && (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-full" />
            </div>
          )}
          {error && <FetchError message={`Failed to load: ${error}`} onRetry={() => void fetchChecklist()} />}
          {data && data.source_state === "artifact_missing" && (
            <EmptyState
              icon={AlertTriangle}
              heading="PRISMA source manuscript artifact is missing."
              sub="Run may not have reached writing/finalize yet, or manuscript artifacts are unavailable for this run."
              className="py-10"
            />
          )}
          {data && data.source_state !== "artifact_missing" && (
            <>
              {/* Summary bar */}
            <div className="flex items-center gap-4 text-xs flex-wrap p-3 rounded-lg glass-panel">
                <span className="text-emerald-400 font-semibold">{data.reported_count} Reported</span>
                <span className="text-amber-400 font-semibold">{data.partial_count} Partial</span>
                <span className="text-red-400 font-semibold">{data.missing_count} Missing</span>
                <span className="text-zinc-400 font-semibold">{data.not_applicable_count} N/A</span>
              </div>

              {/* Section filter chips */}
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

              {/* Items */}
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
                        : item.status === "NOT_APPLICABLE"
                        ? "bg-zinc-900/40"
                        : "bg-red-900/10",
                    )}
                  >
                    <PrismaStatusIcon status={item.status} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-zinc-500 shrink-0">{item.item_id}</span>
                        <span className="text-zinc-400 font-medium leading-snug">{item.description}</span>
                        <span className="text-zinc-600 ml-auto shrink-0">{item.section}</span>
                      </div>
                      {item.rationale && (
                        <p className="text-zinc-600 mt-0.5 leading-relaxed">{item.rationale}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
    </CollapsibleSection>
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
      setExportError(formatExportError(error))
      onExportReadyChange?.(false)
      setExportState("error")
    }
  }, [exportRunId, onExportReadyChange])

  // Auto-trigger export once when the component mounts and a run is ready.
  // handleExport is async and sets state only after the await resolves, so
  // there is no synchronous setState-in-render risk. The eslint rule fires
  // because the linter sees setState reachable from the effect body, but
  // this is intentional: the effect kicks off an async API call whose
  // completion updates the UI state.
  useEffect(() => {
    if (canExport && exportState === "idle") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void handleExport()
    }
  }, [canExport, exportState, handleExport])

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

  const sharedCls = "h-7 gap-1 text-xs border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-500"

  return (
    <div className="flex items-center gap-1.5">
      {/* Packaging spinner shown while auto-export is in flight */}
      {exportState === "loading" && (
        <span className="flex items-center gap-1 text-xs text-zinc-500">
          <Loader2 className="h-3 w-3 animate-spin" />
          Packaging...
        </span>
      )}

      {/* Retry button on failure */}
      {exportState === "error" && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => void handleExport()}
            className={sharedCls}
          >
            <AlertTriangle className="h-3 w-3 text-red-400" />
            Retry export
          </Button>
          {exportError && (
            <span className="text-xs text-red-400 max-w-[28rem] truncate" title={exportError}>
              {exportError}
            </span>
          )}
        </div>
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
                <FileType className="h-3 w-3 text-blue-400" />
                DOCX
              </a>
            </Button>
          )}
          {exportState === "done" && (
            <Button
              size="sm"
              onClick={() => { setExportState("idle"); void handleExport(true); }}
              className="h-7 gap-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-zinc-100 border-0 shadow-none"
              title="Regenerate manuscript .tex and DOCX"
            >
              <RefreshCw className="h-3 w-3 text-emerald-400" />
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
  historyOutputs?: Record<string, string>
  exportRunId?: string | null
  submissionFocusTarget?: "reference-papers" | null
  submissionFocusToken?: number
}

export function ResultsView({
  outputs,
  isDone,
  historyOutputs = {},
  exportRunId,
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
  const [submissionReady, setSubmissionReady] = useState(false)

  const hasSubmissionArtifacts = useCallback((obj: unknown): boolean => {
    if (typeof obj === "string" && isFilePath(obj)) {
      return /\/submission\//.test(obj)
    }
    if (obj && typeof obj === "object" && !Array.isArray(obj)) {
      for (const value of Object.values(obj as Record<string, unknown>)) {
        if (hasSubmissionArtifacts(value)) return true
      }
    }
    return false
  }, [])

  const manuscriptPath = useMemo(
    () => findFileByName(effectiveOutputs, "doc_manuscript"),
    [effectiveOutputs],
  )

  const docxPath = useMemo(
    () => findFileByName(effectiveOutputs, ".docx"),
    [effectiveOutputs],
  )

  // Paths to exclude from Artifacts panel (they live in the left panel header actions)
  const manuscriptExcludePaths = useMemo<Set<string>>(() => {
    const paths = new Set<string>()
    if (manuscriptPath) paths.add(manuscriptPath)
    if (docxPath) paths.add(docxPath)
    const texFiles = findAllFilesByExt(effectiveOutputs, [".tex"])
    texFiles.forEach((p) => paths.add(p))
    return paths
  }, [effectiveOutputs, manuscriptPath, docxPath])

  useEffect(() => {
    setSubmissionReady(hasSubmissionArtifacts(effectiveOutputs))
  }, [effectiveOutputs, hasSubmissionArtifacts])

  useEffect(() => {
    if (submissionFocusTarget && !artifactsOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional one-way sync from navigation focus token
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

      {exportRunId ? (
        <PrismaCard runId={exportRunId} />
      ) : (
        <div className="card-surface px-4 py-3 text-xs text-zinc-500">
          PRISMA compliance available after run completes.
        </div>
      )}

      {exportRunId ? <EvidenceNetworkSection runId={exportRunId} /> : null}

      <CollapsibleSection
        icon={FileText}
        title="Artifacts"
        description="Protocol, data files, figures"
        open={artifactsOpen}
        onToggle={() => setArtifactsOpen((v) => !v)}
        actions={
          exportRunId ? (
            submissionReady ? (
              <Button
                size="sm"
                asChild
                className="h-7 gap-1 text-xs bg-emerald-600 hover:bg-emerald-500 text-zinc-950 border-0 shadow-none"
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
                className="h-7 gap-1 text-xs bg-zinc-800 text-zinc-400 border-0 shadow-none cursor-not-allowed"
                title="Run manuscript export first"
              >
                <Download className="h-3 w-3" />
                Submission Package
              </Button>
            )
          ) : null
        }
      >
        <div className="p-4">
          <ResultsPanel
            outputs={effectiveOutputs}
            excludePaths={manuscriptExcludePaths}
            runId={exportRunId}
            submissionFocusTarget={submissionFocusTarget}
            submissionFocusToken={submissionFocusToken}
          />
        </div>
      </CollapsibleSection>
    </div>
  )
}
