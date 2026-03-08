import { useCallback, useEffect, useState } from "react"
import { BookOpen, Download, ExternalLink, FileText, FileX, RefreshCw } from "lucide-react"
import { fetchPapersReference, fetchPdfsForRun, paperFileUrl } from "@/lib/api"
import type { FetchPdfsProgressEvent, FetchPdfsResult, PaperReference } from "@/lib/api"
import { cn } from "@/lib/utils"

interface ReferencesViewProps {
  runId: string
  isDone: boolean
}

function SourceBadge({ source }: { source: string }) {
  const label =
    source === "abstract"
      ? "Abstract only"
      : source === "landing_page_pdf" || source === "url_direct_pdf"
        ? "Publisher Page (PDF)"
        : source === "landing_page_text" || source === "url_direct_text" || source === "landing_page"
          ? "Publisher Page (Text)"
          : source.startsWith("unpaywall")
            ? "Unpaywall"
            : source.startsWith("semantic")
              ? "Semantic Scholar"
              : source.startsWith("pmc")
                ? "PMC"
                : source.startsWith("core")
                  ? "CORE"
                  : source.startsWith("europepmc")
                    ? "Europe PMC"
                    : source.startsWith("sciencedirect")
                      ? "ScienceDirect"
                      : source.startsWith("arxiv")
                        ? "arXiv"
                        : source.startsWith("biorxiv") || source.startsWith("medrxiv")
                          ? "bioRxiv/medRxiv"
                          : source.startsWith("crossref")
                            ? "Crossref"
                            : source

  const isAbstract = source === "abstract"
  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono",
        isAbstract
          ? "bg-zinc-800 text-zinc-500"
          : "bg-emerald-900/40 text-emerald-400",
      )}
    >
      {label}
    </span>
  )
}

interface FetchProgress {
  current: number
  total: number
  currentTitle: string
  succeeded: number
  failed: number
  skipped: number
}

export function ReferencesView({ runId, isDone }: ReferencesViewProps) {
  const [papers, setPapers] = useState<PaperReference[]>([])
  const [loading, setLoading] = useState(isDone)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)
  const [fetchProgress, setFetchProgress] = useState<FetchProgress | null>(null)
  const [fetchResult, setFetchResult] = useState<FetchPdfsResult | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const fetchPapers = useCallback(() => {
    return fetchPapersReference(runId)
      .then(setPapers)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load references"))
      .finally(() => setLoading(false))
  }, [runId])

  useEffect(() => {
    if (!isDone) return
    setLoading(true)
    void fetchPapers()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDone, runId, refreshKey])

  const handleFetchPdfs = () => {
    setFetching(true)
    setFetchError(null)
    setFetchResult(null)
    setFetchProgress(null)

    const onProgress = (evt: FetchPdfsProgressEvent) => {
      setFetchProgress(prev => ({
        current: evt.current,
        total: evt.total,
        currentTitle: evt.title,
        succeeded: (prev?.succeeded ?? 0) + (evt.status === "ok" ? 1 : 0),
        failed: (prev?.failed ?? 0) + (evt.status === "failed" ? 1 : 0),
        skipped: (prev?.skipped ?? 0) + (evt.status === "skipped" ? 1 : 0),
      }))
    }

    fetchPdfsForRun(runId, onProgress)
      .then((result) => {
        setFetchResult(result)
        setFetchProgress(null)
        setRefreshKey((k) => k + 1)
      })
      .catch((e: unknown) => setFetchError(e instanceof Error ? e.message : "PDF fetch failed"))
      .finally(() => setFetching(false))
  }

  if (!isDone) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-zinc-500 gap-2">
        <BookOpen className="h-8 w-8 opacity-30" />
        <p className="text-sm">References are available after the run completes.</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-zinc-500 text-sm">
        Loading references...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-red-400 gap-2">
        <FileX className="h-8 w-8 opacity-50" />
        <p className="text-sm">{error}</p>
      </div>
    )
  }

  if (papers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-48 text-zinc-500 gap-2">
        <BookOpen className="h-8 w-8 opacity-30" />
        <p className="text-sm">No included papers found for this run.</p>
      </div>
    )
  }

  const someFilesMissing = papers.length > 0 && papers.some((p) => !p.has_file)

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-zinc-200">
            Included Studies
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            {papers.length} {papers.length === 1 ? "paper" : "papers"} included in this review
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500/60" />
              Full text available
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-zinc-600" />
              Abstract only
            </span>
          </div>
          {(someFilesMissing || fetchResult) && (
            <button
              onClick={handleFetchPdfs}
              disabled={fetching}
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors",
                fetching
                  ? "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                  : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 hover:text-zinc-100",
              )}
            >
              <RefreshCw className={cn("h-3 w-3", fetching && "animate-spin")} />
              {fetching ? "Fetching..." : "Fetch PDFs"}
            </button>
          )}
          {/* Live progress during fetch */}
          {fetching && fetchProgress && (
            <div className="flex flex-col items-end gap-1 w-56">
              <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-600 transition-all duration-300"
                  style={{ width: `${Math.round((fetchProgress.current / fetchProgress.total) * 100)}%` }}
                />
              </div>
              <p className="text-[11px] text-zinc-500 text-right">
                {fetchProgress.current} / {fetchProgress.total} papers
                {fetchProgress.succeeded > 0 && (
                  <span className="text-emerald-500 ml-1">-- {fetchProgress.succeeded} retrieved</span>
                )}
              </p>
              <p className="text-[11px] text-zinc-600 text-right truncate max-w-[14rem]" title={fetchProgress.currentTitle}>
                {fetchProgress.currentTitle}
              </p>
            </div>
          )}
          {/* Waiting for first event */}
          {fetching && !fetchProgress && (
            <p className="text-[11px] text-zinc-500">Connecting...</p>
          )}
          {fetchResult && !fetching && (
            <p className="text-[11px] text-zinc-500">
              Retrieved {fetchResult.succeeded} of {fetchResult.attempted} --{" "}
              {fetchResult.failed > 0 ? `${fetchResult.failed} unavailable` : "all found"}
              {fetchResult.skipped > 0 ? `, ${fetchResult.skipped} already saved` : ""}
            </p>
          )}
          {fetchError && !fetching && (
            <p className="text-[11px] text-red-400">{fetchError}</p>
          )}
        </div>
      </div>

      {/* Paper cards */}
      <div className="flex flex-col gap-3">
        {papers.map((paper, idx) => (
          <PaperCard
            key={paper.paper_id}
            paper={paper}
            index={idx + 1}
            runId={runId}
          />
        ))}
      </div>

      {/* Note on full-text availability */}
      <p className="text-xs text-zinc-600 border-t border-zinc-800 pt-3 mt-1">
        Full-text files are saved to the run directory during extraction. Papers showing
        "Abstract only" were extracted from abstract and metadata; no full-text PDF was
        retrieved for those studies.
      </p>
    </div>
  )
}

interface PaperCardProps {
  paper: PaperReference
  index: number
  runId: string
}

function PaperCard({ paper, index, runId }: PaperCardProps) {
  const hasFullText = paper.has_file && paper.file_type != null

  return (
    <div
      className={cn(
        "group relative rounded-lg border p-4 transition-colors",
        hasFullText
          ? "border-zinc-700/60 bg-zinc-900/40 hover:border-zinc-600"
          : "border-zinc-800/60 bg-zinc-900/20",
      )}
    >
      <div className="flex items-start gap-3">
        {/* Index badge */}
        <span className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-zinc-800 text-zinc-400 text-xs font-mono flex items-center justify-center">
          {index}
        </span>

        <div className="flex-1 min-w-0">
          {/* Title */}
          <p className="text-sm font-medium text-zinc-200 leading-snug">
            {paper.title || "Untitled"}
          </p>

          {/* Authors + year */}
          {(paper.authors || paper.year) && (
            <p className="text-xs text-zinc-500 mt-1 truncate">
              {paper.authors && (
                <span>{paper.authors}</span>
              )}
              {paper.authors && paper.year && <span className="mx-1">--</span>}
              {paper.year && <span>{paper.year}</span>}
            </p>
          )}

          {/* Badges row */}
          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            <SourceBadge source={paper.retrieval_source} />
            {paper.source_database && (
              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-zinc-800 text-zinc-500">
                {paper.source_database}
              </span>
            )}
            {paper.file_type === "pdf" && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-900/40 text-blue-400">
                <FileText className="h-2.5 w-2.5" />
                PDF
              </span>
            )}
            {paper.file_type === "txt" && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-violet-900/40 text-violet-400">
                <FileText className="h-2.5 w-2.5" />
                TXT
              </span>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          {paper.doi && (
            <a
              href={`https://doi.org/${paper.doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
              title={`Open DOI: ${paper.doi}`}
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
          {!paper.doi && paper.url && (
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
              title="Open source URL"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
          {hasFullText && (
            <a
              href={paperFileUrl(runId, paper.paper_id)}
              download
              className="p-1.5 rounded text-emerald-600 hover:text-emerald-400 hover:bg-zinc-800 transition-colors"
              title={`Download ${paper.file_type === "pdf" ? "PDF" : "full text"}`}
            >
              <Download className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>
    </div>
  )
}
