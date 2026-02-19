import { RunForm } from "@/components/RunForm"
import type { RunRequest } from "@/lib/api"

interface SetupViewProps {
  defaultReviewYaml: string
  onSubmit: (req: RunRequest) => Promise<void>
  disabled: boolean
}

export function SetupView({ defaultReviewYaml, onSubmit, disabled }: SetupViewProps) {
  return (
    <div className="max-w-2xl mx-auto pt-2 pb-16">
      <div className="mb-6">
        <h2 className="text-base font-semibold text-zinc-200">Configure your review</h2>
        <p className="text-xs text-zinc-500 mt-1">
          Paste your review.yaml and API keys, then start.
        </p>
      </div>
      <RunForm
        defaultReviewYaml={defaultReviewYaml}
        onSubmit={onSubmit}
        disabled={disabled}
      />
    </div>
  )
}
