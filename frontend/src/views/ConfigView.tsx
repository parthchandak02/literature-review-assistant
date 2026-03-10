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
    <div className="flex flex-col gap-4 max-w-5xl">
      <div className="card-surface overflow-hidden">
        <div className="glass-toolbar px-4 py-3 border-b border-zinc-800/70">
          <h3 className="text-sm font-semibold text-zinc-200">Research Question</h3>
        </div>
        <div className="px-4 py-4">
          <p className="text-sm text-zinc-100 leading-relaxed">{researchQuestion}</p>
          {createdAt && (
            <div className="mt-2 inline-flex items-center gap-1.5 glass-chip text-zinc-300">
              <Clock className="h-3.5 w-3.5 text-zinc-400" />
              <span className="text-xs">Run completed {formatRunDate(createdAt)}</span>
            </div>
          )}
        </div>
      </div>

      {yamlContent && (
        <div className="card-surface overflow-hidden">
          <div className="glass-toolbar flex items-center justify-between px-4 py-3 border-b border-zinc-800/70">
            <h3 className="text-sm font-semibold text-zinc-200">Review Config (YAML)</h3>
            <span className="text-xs text-zinc-500">Timestamped config used for this run</span>
          </div>
          <pre className="px-4 py-4 text-xs font-mono text-zinc-200 whitespace-pre-wrap break-words max-h-[62vh] overflow-y-auto leading-relaxed">
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
