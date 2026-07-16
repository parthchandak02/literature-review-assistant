import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { BookOpen, Download, ExternalLink, FileText, FileX, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { EmptyState, FetchError, LoadingPane, Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { fetchPdfsForRun, paperFileUrl } from "@/lib/api"
import type { FetchPdfsProgressEvent, FetchPdfsResult, PaperReference } from "@/lib/api"
import { referencesQueryKey, useReferences } from "@/hooks/useReferences"
import { cn } from "@/lib/utils"

interface ReferencesViewProps {
  runId: string
  /** workflow_id (e.g. wf-0007) for 404 retry when runId evicted from _active_runs */
  workflowId?: string | null
  isDone: boolean
  onGoToSubmissionReferencePapers?: () => void
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
        "glass-chip inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono",
        isAbstract
          ? "text-muted"
          : "text-intent-success border-intent-success-border",
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

export function ReferencesView({
  runId,
  workflowId,
  isDone,
  onGoToSubmissionReferencePapers,
}: ReferencesViewProps) {
  const queryClient = useQueryClient()
  const [fetching, setFetching] = useState(false)
  const [fetchProgress, setFetchProgress] = useState<FetchProgress | null>(null)
  const [fetchResult, setFetchResult] = useState<FetchPdfsResult | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  /** For historical runs, use workflowId (registry-stable); for live runs use runId */
  const effectiveId = (isDone && workflowId) ? workflowId : runId

  const referencesQuery = useReferences(effectiveId, workflowId, { enabled: isDone })
  const papers = referencesQuery.data ?? []
  const loading = referencesQuery.isLoading
  const error = referencesQuery.isError
    ? referencesQuery.error instanceof Error
      ? referencesQuery.error.message
      : "Failed to load references"
    : null

  const refetchPapers = () => {
    void referencesQuery.refetch()
  }

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

    fetchPdfsForRun(effectiveId, onProgress, workflowId)
      .then((result) => {
        setFetchResult(result)
        setFetchProgress(null)
        void queryClient.invalidateQueries({
          queryKey: referencesQueryKey(effectiveId, workflowId),
        })
      })
      .catch((e: unknown) => setFetchError(e instanceof Error ? e.message : "PDF fetch failed"))
      .finally(() => setFetching(false))
  }

  if (!isDone) {
    return (
      <EmptyState
        icon={BookOpen}
        heading="References are available after the run completes."
        className="h-48 py-0"
      />
    )
  }

  if (loading) {
    return <LoadingPane message="Loading references..." className="h-48" />
  }

  if (error) {
    return (
      <div className="py-8">
        <FetchError message={error} onRetry={refetchPapers} />
      </div>
    )
  }

  if (papers.length === 0) {
    return (
      <EmptyState icon={FileX} heading="No included papers found for this run." className="h-48 py-0" />
    )
  }

  const someFilesMissing = papers.length > 0 && papers.some((p) => !p.has_file)
  const abstractOnlyCount = papers.length - papers.filter((p) => p.has_file).length
  const fetchProgressPercent =
    fetchProgress && fetchProgress.total > 0
      ? Math.round((fetchProgress.current / fetchProgress.total) * 100)
      : 0
  const showFetchMeta = fetching || fetchResult != null || fetchError != null

  return (
    <div className="flex flex-col gap-4">
      <div className="card-surface overflow-hidden">
        <ViewToolbar
          className="!h-auto py-3 items-start"
          title={
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-foreground">Included Studies</h2>
              <p className="text-xs text-muted mt-0.5 font-normal">
                {papers.length} {papers.length === 1 ? "paper" : "papers"} included in this review
                {abstractOnlyCount > 0 && (
                  <span className="text-intent-warning ml-1">
                    -- {abstractOnlyCount} without full text (abstract-only extraction)
                  </span>
                )}
              </p>
            </div>
          }
          actions={
            <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
              <div className="flex items-center gap-3 text-[11px] text-muted">
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-intent-success" />
                  Full text
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-surface-4" />
                  Abstract only
                </span>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={onGoToSubmissionReferencePapers}
                className="border-border text-foreground hover:text-foreground"
              >
                Download All
              </Button>
              {(someFilesMissing || fetchResult) && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleFetchPdfs}
                  disabled={fetching}
                  className="border-border text-foreground hover:text-foreground"
                >
                  {fetching ? <Spinner size="sm" /> : <RefreshCw className="h-3 w-3" />}
                  {fetching ? "Fetching..." : "Fetch PDFs"}
                </Button>
              )}
            </div>
          }
        />

        {showFetchMeta && (
          <div className="border-t border-border/70 px-4 py-2.5">
            {fetching && fetchProgress && (
              <div className="flex flex-col gap-1.5 max-w-md ml-auto">
                <div className="h-1 overflow-hidden rounded-full bg-surface-3/40">
                  <div
                    className="h-full bg-intent-active transition-all duration-300"
                    style={{ width: `${fetchProgressPercent}%` }}
                  />
                </div>
                <p className="text-[11px] text-muted text-right tabular-nums">
                  {fetchProgress.current} / {fetchProgress.total} papers
                  {fetchProgress.succeeded > 0 && (
                    <span className="text-intent-success ml-1">
                      -- {fetchProgress.succeeded} retrieved
                    </span>
                  )}
                </p>
                <p
                  className="text-[11px] text-muted text-right truncate"
                  title={fetchProgress.currentTitle}
                >
                  {fetchProgress.currentTitle}
                </p>
              </div>
            )}
            {fetching && !fetchProgress && (
              <p className="text-[11px] text-muted text-right">Connecting...</p>
            )}
            {fetchResult && !fetching && (
              <p className="text-[11px] text-muted text-right">
                Retrieved {fetchResult.succeeded} of {fetchResult.attempted} --{" "}
                {fetchResult.failed > 0 ? `${fetchResult.failed} unavailable` : "all found"}
                {fetchResult.skipped > 0 ? `, ${fetchResult.skipped} already saved` : ""}
              </p>
            )}
            {fetchError && !fetching && (
              <p className="text-[11px] text-intent-danger text-right">{fetchError}</p>
            )}
          </div>
        )}
      </div>

      {/* Paper cards */}
      <div className="flex flex-col gap-3">
        {papers.map((paper, idx) => (
          <PaperCard
            key={paper.paper_id}
            paper={paper}
            index={idx + 1}
            runId={effectiveId}
          />
        ))}
      </div>

      {/* Note on full-text availability */}
      <p className="text-xs text-muted border-t border-border pt-3 mt-1">
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
        "group relative p-4 transition-colors data-surface",
        hasFullText && "hover:border-border",
      )}
    >
      <div className="flex items-start gap-3">
        {/* Index badge */}
        <span className="shrink-0 mt-0.5 w-6 h-6 rounded-full bg-surface-2 text-muted text-xs font-mono flex items-center justify-center">
          {index}
        </span>

        <div className="flex-1 min-w-0">
          {/* Title */}
          <p className="text-sm font-medium text-foreground leading-snug">
            {paper.title || "Untitled"}
          </p>

          {/* Authors + year */}
          {(paper.authors || paper.year) && (
            <p className="text-xs text-muted mt-1 truncate">
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
            <span className="glass-chip inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono text-muted">
                {paper.source_database}
              </span>
            )}
            {paper.file_type === "pdf" && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-intent-info-subtle text-intent-info">
                <FileText className="h-2.5 w-2.5" />
                PDF
              </span>
            )}
            {paper.file_type === "txt" && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-mono bg-intent-primary-subtle text-intent-primary">
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
              className="p-1.5 rounded text-muted hover:text-foreground hover:bg-surface-2 transition-colors"
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
              className="p-1.5 rounded text-muted hover:text-foreground hover:bg-surface-2 transition-colors"
              title="Open source URL"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
          {hasFullText && (
            <a
              href={paperFileUrl(runId, paper.paper_id)}
              download
              className="p-1.5 rounded text-intent-success hover:text-intent-success hover:bg-surface-2 transition-colors"
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
