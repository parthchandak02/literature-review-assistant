import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeSlug from "rehype-slug"
import rehypeAutolinkHeadings from "rehype-autolink-headings"
import rehypeHighlight from "rehype-highlight"
import { BookOpen } from "lucide-react"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"
import { FetchError, Spinner } from "@/components/ui/feedback"
import { ViewToolbar } from "@/components/ui/view-toolbar"
import { ManuscriptImage } from "@/components/ManuscriptImage"
import { fetchArtifactText } from "@/lib/api"
import { extractHeadings, makeUrlTransform } from "./manuscriptUtils"

export function ManuscriptViewer({ filePath }: { filePath: string }) {
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
      <ViewToolbar
        dense
        title={
          <button
            type="button"
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
        }
        actions={
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(70, z - 15))}
              disabled={zoom <= 70}
              className="w-6 h-6 rounded text-sm font-mono text-muted hover:text-foreground hover:bg-surface-2 disabled:opacity-30 transition-colors"
            >
              -
            </button>
            <span className="text-xs font-mono text-muted w-10 text-center tabular-nums">{zoom}%</span>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(160, z + 15))}
              disabled={zoom >= 160}
              className="w-6 h-6 rounded text-sm font-mono text-muted hover:text-foreground hover:bg-surface-2 disabled:opacity-30 transition-colors"
            >
              +
            </button>
          </div>
        }
      />

      {/* Vertical outline panel -- collapsible */}
      {showOutline && headings.length > 0 && (
        <ViewToolbar className="!h-auto max-h-52 overflow-y-auto block">
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
        </ViewToolbar>
      )}

      {/* Manuscript body */}
      <div ref={viewerRef} className="overflow-auto max-h-[70vh] p-6 md:p-10">
        <div className="manuscript-prose max-w-3xl mx-auto manuscript-viewer" style={{ fontSize: `${zoom}%` }}>
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
