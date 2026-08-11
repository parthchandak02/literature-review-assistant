import { AlertTriangle, CheckCircle, Circle, MinusCircle } from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { cn } from "@/lib/utils"

export type ConfigGenStepStatus = "done" | "degraded" | "skipped" | "active" | "pending"

export interface ConfigGenStepDisplay {
  key: string
  label: string
  shortLabel: string
  detail?: string | null
  status: ConfigGenStepStatus
}

interface ConfigGenerationStepperProps {
  steps: ConfigGenStepDisplay[]
}

function ConfigGenStep({
  step,
  isLast,
}: {
  step: ConfigGenStepDisplay
  isLast: boolean
}) {
  const { status } = step

  const circleCls = cn(
    "w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center border shrink-0",
    status === "done" && "bg-intent-success-subtle border-intent-success-border text-intent-success",
    status === "active" && "bg-intent-active-subtle border-intent-active-border text-intent-active",
    status === "degraded" && "bg-intent-warning-subtle border-intent-warning-border text-intent-warning",
    status === "skipped" && "bg-intent-info-subtle border-intent-info-border text-intent-info",
    status === "pending" && "bg-card border-border text-muted",
  )

  const connectorCls = cn(
    "h-px shrink-0",
    status === "done" ? "bg-intent-success" :
    status === "active" ? "bg-intent-active" :
    status === "degraded" ? "bg-intent-warning" :
    status === "skipped" ? "bg-intent-info" :
    "bg-border",
  )

  const labelCls = cn(
    "text-[10px] sm:text-[11px] text-center leading-tight font-medium px-0 mt-1.5",
    status === "done" && "text-foreground",
    status === "active" && "text-intent-active",
    status === "degraded" && "text-intent-warning",
    status === "skipped" && "text-intent-info",
    status === "pending" && "text-muted",
  )

  return (
    <div className="relative flex flex-1 min-w-0 items-start py-1">
      <div
        className="flex flex-col items-center w-full shrink-0"
        title={step.detail ?? step.label}
      >
        <div className={circleCls}>
          {status === "done" ? (
            <CheckCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : status === "active" ? (
            <Spinner size="md" />
          ) : status === "degraded" ? (
            <AlertTriangle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : status === "skipped" ? (
            <MinusCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
          ) : (
            <Circle className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
          )}
        </div>
        <span className={labelCls}>{step.shortLabel}</span>
        {step.detail && status !== "pending" && (
          <span
            className={cn(
              "text-[9px] sm:text-[10px] mt-0.5 text-center leading-snug px-0.5 line-clamp-3",
              status === "active" ? "text-foreground/80 block" : "text-muted hidden lg:block",
            )}
          >
            {step.detail}
          </span>
        )}
      </div>
      {!isLast && (
        <div className={cn("relative flex-1 mt-3.5 sm:mt-4", connectorCls)} style={{ minWidth: "0.35rem" }} />
      )}
    </div>
  )
}

export function ConfigGenerationStepper({ steps }: ConfigGenerationStepperProps) {
  return (
    <div className="overflow-hidden py-2 sm:py-3">
      <div className="flex items-start w-full gap-0.5 sm:gap-1">
        {steps.map((step, i) => (
          <ConfigGenStep key={step.key} step={step} isLast={i === steps.length - 1} />
        ))}
      </div>
    </div>
  )
}
