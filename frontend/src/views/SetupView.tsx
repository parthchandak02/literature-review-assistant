import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { fetchRunConfig } from "@/lib/api"
import type { HistoryEntry } from "@/lib/api"
import { useHistory } from "@/hooks/useHistory"
import { runConfigQueryKey } from "@/hooks/useRunConfig"
import { QuestionStage } from "@/components/setup/QuestionStage"
import { ReviewTypeDecisionStage } from "@/components/setup/ReviewTypeDecisionStage"
import type { ReviewTypeChoice, SetupViewProps } from "@/components/setup/types"

export type { ConfigGenerateRequest, CsvMode, GenerationProfile, ReviewTypeChoice } from "@/components/setup/types"
export { ConfigReviewStage } from "@/components/setup/ConfigReviewStage"

type SetupStep = "review_type" | "question"

export function SetupView({
  defaultReviewYaml,
  onGenerateDraft,
  onOpenDraftWithYaml,
  disabled,
}: SetupViewProps) {
  const queryClient = useQueryClient()
  const { data: history = [], error: historyError } = useHistory()
  const [setupStep, setSetupStep] = useState<SetupStep>("review_type")
  const [reviewType, setReviewType] = useState<ReviewTypeChoice | null>(null)
  const [researchQuestion, setResearchQuestion] = useState("")
  const [pendingFireworksKey, setPendingFireworksKey] = useState("")
  const [pendingCsvFile, setPendingCsvFile] = useState<File | null>(null)
  const [pendingCsvMode, setPendingCsvMode] = useState<"supplementary" | "masterlist">("supplementary")
  const [loadingHistoryId, setLoadingHistoryId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const historyLoadError = historyError
    ? (historyError instanceof Error ? historyError.message : "Failed to load review history.")
    : null

  function handlePasteYaml() {
    onOpenDraftWithYaml(defaultReviewYaml)
  }

  async function handleLoadFromHistory(entry: HistoryEntry) {
    setLoadError(null)
    setLoadingHistoryId(entry.workflow_id)
    try {
      const yaml = await queryClient.fetchQuery({
        queryKey: runConfigQueryKey(entry.workflow_id),
        queryFn: () => fetchRunConfig(entry.workflow_id),
      })
      if (!yaml) {
        setLoadError(
          "Config not saved for that run. Only runs started recently can be reloaded.",
        )
        return
      }
      onOpenDraftWithYaml(yaml)
    } catch {
      setLoadError("Failed to load config for that run.")
    } finally {
      setLoadingHistoryId(null)
    }
  }

  return (
    <div className="max-w-xl mx-auto pt-6 pb-16 px-4" aria-disabled={disabled}>
      {setupStep === "review_type" ? (
        <ReviewTypeDecisionStage
          onComplete={(selectedReviewType) => {
            setReviewType(selectedReviewType)
            setSetupStep("question")
          }}
        />
      ) : reviewType ? (
        <QuestionStage
          reviewType={reviewType}
          onBack={() => setSetupStep("review_type")}
          onGenerateRequested={(req) => {
            setResearchQuestion(req.question)
            setPendingFireworksKey(req.fireworksKey)
            setPendingCsvFile(req.csvFile ?? null)
            setPendingCsvMode(req.csvMode)
            onGenerateDraft(req)
          }}
          onPasteYaml={handlePasteYaml}
          history={history}
          onLoadFromHistory={(entry) => void handleLoadFromHistory(entry)}
          loadingHistoryId={loadingHistoryId}
          loadError={loadError ?? historyLoadError}
          onClearError={() => setLoadError(null)}
          initialQuestion={researchQuestion}
          initialFireworksKey={pendingFireworksKey}
          initialCsvFile={pendingCsvFile}
          initialCsvMode={pendingCsvMode}
        />
      ) : null}
    </div>
  )
}
