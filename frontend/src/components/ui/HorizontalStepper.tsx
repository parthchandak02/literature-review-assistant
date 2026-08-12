import {
  AlertCircle,
  AlertTriangle,
  CheckCircle,
  Circle,
  MinusCircle,
  XCircle,
} from "lucide-react"
import { Spinner } from "@/components/ui/feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export type StepperStepStatus =
  | "done"
  | "active"
  | "awaiting"
  | "warning"
  | "skipped"
  | "error"
  | "pending"

export interface StepperStep {
  key: string
  label: string
  status: StepperStepStatus
  title?: string
  onClick?: () => void
  clickable?: boolean
  armed?: boolean
  rangeHighlight?: "start" | "middle" | "end" | "single"
}

export interface HorizontalStepperProps {
  steps: StepperStep[]
  loading?: boolean
  loadingStepCount?: number
}

function statusCircleClass(status: StepperStepStatus): string {
  return cn(
    "w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center border shrink-0",
    status === "done" && "bg-intent-success-subtle border-intent-success-border text-intent-success",
    status === "active" && "bg-intent-active-subtle border-intent-active-border text-intent-active",
    status === "awaiting" && "bg-intent-warning-subtle border-intent-warning-border text-intent-warning",
    status === "warning" && "bg-intent-warning-subtle border-intent-warning-border text-intent-warning",
    status === "skipped" && "bg-intent-info-subtle border-intent-info-border text-intent-info",
    status === "error" && "bg-intent-danger-subtle border-intent-danger-border text-intent-danger",
    status === "pending" && "bg-card border-border text-muted",
  )
}

function statusConnectorClass(status: StepperStepStatus): string {
  return cn(
    "h-px shrink-0",
    status === "done" ? "bg-intent-success" :
    status === "active" ? "bg-intent-active" :
    status === "awaiting" || status === "warning" ? "bg-intent-warning" :
    status === "skipped" ? "bg-intent-info" :
    "bg-border",
  )
}

function statusLabelClass(status: StepperStepStatus): string {
  return cn(
    "text-[10px] sm:text-[11px] text-center leading-tight font-medium px-0 mt-1.5",
    status === "done" && "text-foreground",
    status === "active" && "text-intent-active",
    (status === "awaiting" || status === "warning") && "text-intent-warning",
    status === "skipped" && "text-intent-info",
    status === "error" && "text-intent-danger",
    status === "pending" && "text-muted",
  )
}

function StepIcon({ status }: { status: StepperStepStatus }) {
  if (status === "done") return <CheckCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
  if (status === "active") return <Spinner size="md" />
  if (status === "awaiting") return <AlertCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
  if (status === "warning") return <AlertTriangle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
  if (status === "skipped") return <MinusCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
  if (status === "error") return <XCircle className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
  return <Circle className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
}

function StepperStepNode({
  step,
  isLast,
}: {
  step: StepperStep
  isLast: boolean
}) {
  const { status, label, title, onClick, clickable, armed, rangeHighlight } = step
  const interactive = Boolean(clickable && onClick)

  const circle = (
    <div
      className={cn(
        statusCircleClass(status),
        interactive && "cursor-pointer transition-colors hover:border-intent-warning-border",
        armed && "border-intent-warning bg-intent-warning-subtle text-intent-warning",
      )}
    >
      <StepIcon status={status} />
    </div>
  )

  return (
    <div className="relative flex flex-1 min-w-0 items-start py-1">
      {rangeHighlight ? (
        <div
          className={cn(
            "absolute left-0 right-0 top-1 h-14 sm:h-14 bg-intent-warning-subtle",
            (rangeHighlight === "start" || rangeHighlight === "single") && "rounded-l-md",
            (rangeHighlight === "end" || rangeHighlight === "single") && "rounded-r-md",
          )}
          aria-hidden
        />
      ) : null}
      <div className="flex flex-col items-center w-full shrink-0" title={title}>
        {interactive ? (
          <button
            type="button"
            onClick={onClick}
            disabled={!clickable}
            className={cn(
              statusCircleClass(status),
              "relative transition-colors",
              clickable && "cursor-pointer hover:border-intent-warning-border",
              armed && "border-intent-warning bg-intent-warning-subtle text-intent-warning",
            )}
            title={title}
          >
            <StepIcon status={status} />
          </button>
        ) : (
          circle
        )}
        <span className={statusLabelClass(status)}>{label}</span>
      </div>
      {!isLast ? (
        <div
          className={cn("relative flex-1 mt-3.5 sm:mt-4", statusConnectorClass(status))}
          style={{ minWidth: "0.35rem" }}
        />
      ) : null}
    </div>
  )
}

export function HorizontalStepper({
  steps,
  loading = false,
  loadingStepCount = 6,
}: HorizontalStepperProps) {
  if (loading) {
    return (
      <div className="overflow-hidden py-2 sm:py-3 flex items-start gap-1">
        {Array.from({ length: loadingStepCount }, (_, i) => (
          <div key={i} className="flex items-start flex-1">
            <div className="flex flex-col items-center gap-1.5 w-full shrink-0">
              <Skeleton className="w-7 h-7 sm:w-8 sm:h-8 rounded-full" />
              <Skeleton className="h-2.5 w-8 sm:w-10" />
            </div>
            {i < loadingStepCount - 1 ? (
              <div className="flex-1 mt-3.5 sm:mt-4 h-px bg-border" />
            ) : null}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="overflow-hidden py-2 sm:py-3">
      <div className="flex items-start w-full gap-0.5 sm:gap-1">
        {steps.map((step, i) => (
          <StepperStepNode key={step.key} step={step} isLast={i === steps.length - 1} />
        ))}
      </div>
    </div>
  )
}
