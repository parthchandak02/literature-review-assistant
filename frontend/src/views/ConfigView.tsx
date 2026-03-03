import { useCallback, useEffect, useState } from "react"
import { Clock, FileCode, Loader2 } from "lucide-react"
import { fetchRunConfig } from "@/lib/api"
import { formatRunDate } from "@/lib/format"
import { EmptyState } from "@/components/ui/feedback"

// ---------------------------------------------------------------------------
// ConfigView
// ---------------------------------------------------------------------------

export interface ConfigViewProps {
  /** Workflow ID or run ID for fetching config (API accepts both). */
  workflowId: string
  /** Fallback topic/research question when YAML is not yet available. */
  topic: string
  /** Run completion timestamp for display. */
  createdAt?: string | null
}

export function ConfigView({
  workflowId,
  topic,
  createdAt,
}: ConfigViewProps) {
  const [yamlContent, setYamlContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadConfig = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const content = await fetchRunConfig(workflowId)
      setYamlContent(content)
      if (!content) {
        setError("Config not saved for this run. Older CLI runs may not have review.yaml persisted.")
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load config")
      setYamlContent(null)
    } finally {
      setLoading(false)
    }
  }, [workflowId])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  const researchQuestion =
    yamlContent != null
      ? (() => {
          try {
            const parsed = parseYamlResearchQuestion(yamlContent)
            return parsed ?? topic
          } catch {
            return topic
          }
        })()
      : topic

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-zinc-500">
        <Loader2 className="h-8 w-8 animate-spin" />
        <p className="text-sm">Loading config...</p>
      </div>
    )
  }

  if (error && !yamlContent) {
    return (
      <EmptyState
        icon={FileCode}
        heading="Config not available"
        sub={error}
        className="py-12"
      />
    )
  }

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      {/* Research question + timestamp */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-zinc-300">Research Question</h3>
        <p className="text-sm text-zinc-200 leading-relaxed">{researchQuestion}</p>
        {createdAt && (
          <div className="flex items-center gap-1.5 text-xs text-zinc-500">
            <Clock className="h-3.5 w-3.5" />
            <span>Run completed {formatRunDate(createdAt)}</span>
          </div>
        )}
      </div>

      {/* YAML block */}
      {yamlContent && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-zinc-300">
            Review Config (YAML)
          </h3>
          <p className="text-xs text-zinc-500">
            Timestamped config used for this run. Other agents can refer to this.
          </p>
          <pre className="p-4 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-mono text-zinc-300 whitespace-pre-wrap break-words max-h-[60vh] overflow-y-auto">
            {yamlContent}
          </pre>
        </div>
      )}
    </div>
  )
}

function parseYamlResearchQuestion(yaml: string): string | null {
  const match = yaml.match(/research_question:\s*["']?([^"'\n]+)["']?/)
  return match ? match[1].trim() : null
}
