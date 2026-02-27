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
  PackageCheck,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  BookOpen,
  X,
  Download,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ResultsPanel } from "@/components/ResultsPanel"
import { triggerExport, fetchPrismaChecklist, downloadUrl } from "@/lib/api"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError } from "@/components/ui/feedback"
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

// ---------------------------------------------------------------------------
// Manuscript inline viewer
// ---------------------------------------------------------------------------

function ManuscriptViewer({ filePath }: { filePath: string }) {
  const [content, setContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
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
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
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
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 overflow-hidden">
      {/* TOC bar */}
      {headings.length > 0 && (
        <div className="flex items-center gap-1 px-4 py-2 border-b border-zinc-800 bg-zinc-950/60 overflow-x-auto scrollbar-none">
          <BookOpen className="h-3.5 w-3.5 text-zinc-600 shrink-0 mr-1" />
          {headings.map((h) => (
            <button
              key={h.slug}
              onClick={() => jumpTo(h.slug)}
              className={cn(
                "shrink-0 px-2 py-0.5 rounded text-xs transition-colors whitespace-nowrap",
                h.level === 1
                  ? "text-zinc-200 font-semibold hover:bg-zinc-800"
                  : h.level === 2
                  ? "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
                  : "text-zinc-600 hover:bg-zinc-800 hover:text-zinc-400",
              )}
            >
              {h.text}
            </button>
          ))}
        </div>
      )}

      {/* Manuscript body */}
      <div ref={viewerRef} className="overflow-auto max-h-[70vh] p-6 md:p-10">
        <div className="prose prose-invert prose-zinc max-w-3xl mx-auto">
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
// PRISMA slide-over panel
// ---------------------------------------------------------------------------

function PrismaStatusIcon({ status }: { status: string }) {
  if (status === "REPORTED") return <CheckCircle className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
  if (status === "PARTIAL") return <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />
  return <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
}

function PrismaSlideOver({
  runId,
  onClose,
}: {
  runId: string
  onClose: () => void
}) {
  const [data, setData] = useState<PrismaChecklist | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sectionFilter, setSectionFilter] = useState<string>("All")

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchPrismaChecklist(runId)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [runId])

  const sections = data
    ? ["All", ...Array.from(new Set(data.items.map((i) => i.section)))]
    : ["All"]

  const filtered = data
    ? sectionFilter === "All"
      ? data.items
      : data.items.filter((i) => i.section === sectionFilter)
    : []

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="flex-1 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Panel */}
      <div className="w-full max-w-lg bg-zinc-900 border-l border-zinc-800 flex flex-col h-full shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-zinc-800 shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">PRISMA 2020 Compliance</h2>
            {data && (
              <p className={cn(
                "text-xs font-mono mt-0.5",
                data.passed ? "text-emerald-400" : "text-amber-400",
              )}>
                {data.reported_count}/{data.total} reported --{" "}
                {data.passed ? "PASS" : "needs attention"}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-200 transition-colors p-1 rounded"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading && (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-full" />
            </div>
          )}
          {error && <FetchError message={`Failed to load: ${error}`} />}
          {data && (
            <>
              {/* Summary */}
              <div className="flex items-center gap-4 text-xs flex-wrap p-3 rounded-lg bg-zinc-800/50">
                <span className="text-emerald-400 font-semibold">{data.reported_count} Reported</span>
                <span className="text-amber-400 font-semibold">{data.partial_count} Partial</span>
                <span className="text-red-400 font-semibold">{data.missing_count} Missing</span>
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
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ResultsView
// ---------------------------------------------------------------------------

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
  const [showPrisma, setShowPrisma] = useState(false)
  const [showOtherFiles, setShowOtherFiles] = useState(false)

  const effectiveOutputs = useMemo<Record<string, unknown>>(() => {
    if (Object.keys(outputs).length > 0) return outputs
    if (Object.keys(historyOutputs).length > 0) return { artifacts: historyOutputs }
    return {}
  }, [outputs, historyOutputs])

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

  const manuscriptPath = useMemo(
    () => findFileByName(effectiveOutputs, "doc_manuscript"),
    [effectiveOutputs],
  )

  const docxPath = useMemo(
    () => findFileByName(effectiveOutputs, ".docx"),
    [effectiveOutputs],
  )

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
        <p className="text-zinc-500 text-sm font-medium">Results available once the review completes.</p>
        <p className="text-zinc-600 text-xs max-w-xs leading-relaxed">
          Switch to the Activity tab to monitor progress.
        </p>
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
    <div className="flex flex-col gap-5 max-w-4xl">
      {/* Action bar */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Export to LaTeX */}
        {canExport && (
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
                LaTeX Exported
              </>
            ) : (
              "Export to LaTeX"
            )}
          </Button>
        )}

        {/* Download DOCX */}
        {docxPath && (
          <Button
            size="sm"
            variant="outline"
            asChild
            className="border-zinc-700 text-zinc-300 hover:text-white gap-1.5"
          >
            <a href={downloadUrl(docxPath)} download="manuscript.docx">
              <Download className="h-3.5 w-3.5" />
              Download .docx
            </a>
          </Button>
        )}

        {/* PRISMA checklist button */}
        {exportRunId && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => setShowPrisma(true)}
            className="border-zinc-700 text-zinc-400 hover:text-zinc-200 gap-1.5"
          >
            <CheckCircle className="h-3.5 w-3.5" />
            PRISMA Checklist
          </Button>
        )}

        {/* Export error */}
        {exportState === "error" && exportError && (
          <span className="text-xs text-red-400 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            {exportError}
          </span>
        )}
      </div>

      {/* Manuscript inline reader */}
      {manuscriptPath && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FileText className="h-3.5 w-3.5 text-zinc-500" />
            <span className="text-[11px] font-semibold text-zinc-500 uppercase tracking-wider">
              Manuscript
            </span>
          </div>
          <ManuscriptViewer filePath={manuscriptPath} />
        </div>
      )}

      {/* Other artifacts (collapsible) */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
        <button
          onClick={() => setShowOtherFiles((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-800/30 transition-colors"
        >
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-zinc-500" />
            <span className="text-sm font-medium text-zinc-300">Other Artifacts</span>
            <span className="text-xs text-zinc-600">Protocol, search appendix, data files, figures</span>
          </div>
          {showOtherFiles ? (
            <ChevronUp className="h-4 w-4 text-zinc-600" />
          ) : (
            <ChevronDown className="h-4 w-4 text-zinc-600" />
          )}
        </button>

        {showOtherFiles && (
          <div className="border-t border-zinc-800 p-4">
            <ResultsPanel outputs={mergedOutputs} />
          </div>
        )}
      </div>

      {/* PRISMA slide-over */}
      {showPrisma && exportRunId && (
        <PrismaSlideOver runId={exportRunId} onClose={() => setShowPrisma(false)} />
      )}
    </div>
  )
}
