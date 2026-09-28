import { AlertTriangle, RotateCcw, ScrollText } from "lucide-react"
import { Button } from "@/components/ui/button"
import { phaseLabel } from "@/lib/constants"

export interface FailureBannerProps {
  phase: string | null
  message: string
  resumePhase: string | null
  onShowInLog?: () => void
  onResume?: (phase: string) => void
}

export function FailureBanner({ phase, message, resumePhase, onShowInLog, onResume }: FailureBannerProps) {
  const title = phase ? `Run failed in ${phaseLabel(phase, "long")}` : "Run failed"
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 bg-intent-danger-subtle border border-intent-danger-border rounded-panel px-4 py-3 text-sm"
    >
      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-intent-danger" aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="min-w-0">
          <p className="font-medium text-intent-danger-text">{title}</p>
          <p className="mt-0.5 text-foreground break-words [overflow-wrap:anywhere]">{message}</p>
        </div>
        {onShowInLog || (onResume && resumePhase) ? (
          <div className="flex flex-wrap gap-2">
            {onShowInLog ? (
              <Button type="button" variant="outline" size="xs" onClick={onShowInLog}>
                <ScrollText aria-hidden />
                Show in log
              </Button>
            ) : null}
            {onResume && resumePhase ? (
              <Button type="button" variant="outline" size="xs" onClick={() => onResume(resumePhase)}>
                <RotateCcw aria-hidden />
                Resume from {phaseLabel(resumePhase, "long")}
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  )
}
