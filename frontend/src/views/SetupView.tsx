import { useState } from "react"
import { Activity } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useQueryClient } from "@tanstack/react-query"
import { fetchRunConfig } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import { useHistory } from "@/hooks/useHistory"
import { runConfigQueryKey } from "@/hooks/useRunConfig"
import { QuestionStage } from "@/components/setup/QuestionStage"
import type { SetupViewProps } from "@/components/setup/types"

export type { ConfigGenerateRequest, CsvMode, GenerationProfile, ReviewTypeChoice } from "@/components/setup/types"

export function SetupView({
  defaultReviewYaml,
  onGenerateDraft,
  onOpenDraftWithYaml,
  disabled,
  onOpenLiveRun,
}: SetupViewProps) {
  const queryClient = useQueryClient()
  const { data: history = [], error: historyError } = useHistory()
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [historyErrorDismissed, setHistoryErrorDismissed] = useState(false)
  const historyLoadError = historyError && !historyErrorDismissed
    ? (historyError instanceof Error ? historyError.message : "Failed to load review history.")
    : null

  async function handleLoadFromHistory(entry: HistoryEntry) {
    setLoadError(null)
    setLoadingHistoryId(entry.workflow_id)
    try {
      const yaml = await queryClient.fetchQuery({
        queryKey: runConfigQueryKey(entry.workflow_id),
        queryFn: () => fetchRunConfig(entry.workflow_id),
      })
      if (!yaml) {
        setLoadError("No saved config for that review. Older runs may not have one.")
        return
      }
      onOpenDraftWithYaml(yaml)
    } catch {
      setLoadError("Failed to load config for that review.")
    } finally {
      setLoadingHistoryId(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-xl px-4 pb-16 pt-2 lg:max-w-5xl lg:px-8 lg:pt-4">
      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:items-start lg:gap-12 xl:gap-14">
        <header className="mb-6 lg:sticky lg:top-6 lg:mb-0 lg:pt-2">
          <p className="text-sm text-muted">Literature Review Assistant</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground sm:text-[1.65rem]">
            New review
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
            State your research question. We draft search strategy, screening rules, and the manuscript workflow.
          </p>
        </header>
        <div className="glass-panel-strong p-5 sm:p-6">
      {disabled && (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-intent-warning-border bg-intent-warning-subtle px-3 py-2.5 text-xs text-intent-warning"
        >
          <span className="flex-1 min-w-0">
            A review is already running. Starting a new review is disabled until it finishes or is stopped.
          </span>
          {onOpenLiveRun && (
            <Button type="button" size="xs" variant="outline" onClick={onOpenLiveRun}>
              <Activity className="h-3.5 w-3.5" />
              Open live run
            </Button>
          )}
        </div>
      )}
      <QuestionStage
        disabled={disabled}
        onGenerateRequested={onGenerateDraft}
        onPasteYaml={() => onOpenDraftWithYaml(defaultReviewYaml)}
        history={history}
        onLoadFromHistory={(entry) => void handleLoadFromHistory(entry)}
        loadingHistoryId={loadingHistoryId}
        loadError={loadError ?? historyLoadError}
        onClearError={() => {
          setLoadError(null)
          setHistoryErrorDismissed(true)
        }}
      />
        </div>
      </div>
    </div>
  )
}
