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
  /** Secondary line under the label, e.g. "PDF retrieval · 34/120 · 6m". */
  subStatus?: string | null
  /** Screen-reader status phrase; defaults to one derived from `status`. */
  srStatus?: string
}

export interface HorizontalStepperProps {
  steps: StepperStep[]
  loading?: boolean
  loadingStepCount?: number
  "aria-label"?: string
}

const SR_STATUS: Record<StepperStepStatus, string> = {
  done: "complete",
  active: "in progress",
  awaiting: "waiting on you",
  warning: "complete with warnings",
  skipped: "skipped",
  error: "failed",
  pending: "not started",
}

function statusCircleClass(status: StepperStepStatus): string {
  return cn(
    "relative z-10 w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center border shrink-0",
    status === "done" && "bg-intent-success-subtle border-intent-success-border text-intent-success",
    status === "active" && "bg-intent-active-subtle border-intent-active-border text-intent-active",
    status === "awaiting" && "bg-intent-warning-subtle border-intent-warning-border text-intent-warning",
    status === "warning" && "bg-intent-warning-subtle border-intent-warning-border text-intent-warning",
    status === "skipped" && "bg-intent-info-subtle border-intent-info-border text-intent-info",
    status === "error" && "bg-intent-danger-subtle border-intent-danger-border text-intent-danger",
    status === "pending" && "bg-card border-border-strong text-muted",
  )
}

function isCompleteStatus(status: StepperStepStatus): boolean {
  return status === "done" || status === "warning" || status === "skipped"
}

function statusLabelClass(status: StepperStepStatus): string {
  return cn(
    "text-2xs text-center leading-tight font-medium mt-1.5",
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

/** 2px line from this circle's edge to the next circle's edge, vertically centred on the circles. */
const CONNECTOR_POSITION =
  "absolute h-0.5 top-[calc(0.25rem+0.875rem-1px)] sm:top-[calc(0.25rem+1rem-1px)] left-[calc(50%+1.25rem)] right-[calc(-50%+1.25rem)] rounded-full"

function Connector({ filled }: { filled: boolean }) {
  return (
    <span
      aria-hidden
      data-testid="stepper-connector"
      data-filled={filled ? "true" : "false"}
      className={cn(CONNECTOR_POSITION, filled ? "bg-intent-success" : "bg-border")}
    />
  )
}

function isActiveStatus(status: StepperStepStatus): boolean {
  return status === "active" || status === "awaiting" || status === "error"
}

export function HorizontalStepper({
  steps,
  loading = false,
  loadingStepCount = 6,
  "aria-label": ariaLabel = "Progress",
}: HorizontalStepperProps) {
  if (loading) {
    return (
      <div className="overflow-hidden py-2 sm:py-3 flex items-start" aria-busy="true">
        {Array.from({ length: loadingStepCount }, (_, i) => (
          <div key={i} className="relative flex flex-1 flex-col items-center py-1">
            <Skeleton className="w-7 h-7 sm:w-8 sm:h-8 rounded-full" />
            <Skeleton className="h-2.5 w-8 sm:w-10 mt-1.5" />
            {i < loadingStepCount - 1 ? <Connector filled={false} /> : null}
          </div>
        ))}
      </div>
    )
  }

  const activeIndex = steps.findIndex((step) => isActiveStatus(step.status))

  return (
    <div className="overflow-hidden py-2 sm:py-3">
      <ol className="flex items-start w-full" aria-label={ariaLabel}>
        {steps.map((step, i) => {
          const isLast = i === steps.length - 1
          const isCurrent = i === activeIndex
          const next = steps[i + 1]
          const filled = isCompleteStatus(step.status) && Boolean(next) && next.status !== "pending"
          return (
            <li
              key={step.key}
              className="relative flex flex-1 min-w-0 flex-col items-center py-1"
              aria-current={isCurrent ? "step" : undefined}
              title={step.title}
            >
              <span className={statusCircleClass(step.status)} aria-hidden>
                <StepIcon status={step.status} />
              </span>
              <span className={statusLabelClass(step.status)}>
                <span className={cn(!isCurrent && "max-sm:sr-only")}>{step.label}</span>
                <span className="sr-only">, {step.srStatus ?? SR_STATUS[step.status]}</span>
              </span>
              {step.subStatus ? (
                <span className="mt-0.5 px-1 text-2xs text-center leading-tight text-muted tabular-nums break-words">
                  {step.subStatus}
                </span>
              ) : null}
              {!isLast ? <Connector filled={filled} /> : null}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
