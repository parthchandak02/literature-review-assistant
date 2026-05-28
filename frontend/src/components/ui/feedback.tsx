/**
 * Shared feedback components used across multiple views.
 *
 * Spinner     - inline animated spinner with size variants
 * EmptyState  - centred icon + heading + optional sub-text
 * FetchError  - red alert box with optional retry button
 * LoadingPane - centred spinner for full-pane loading states
 */
import { AlertTriangle, Loader } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

interface SpinnerProps {
  /** xs = 10px, sm = 12px, md = 14–16px (phase timeline), lg = 24px, xl = 32px */
  size?: "xs" | "sm" | "md" | "lg" | "xl"
  className?: string
}

const SPINNER_SIZE: Record<NonNullable<SpinnerProps["size"]>, string> = {
  xs: "h-2.5 w-2.5",
  sm: "h-3 w-3",
  md: "h-3.5 w-3.5 sm:h-4 sm:w-4",
  lg: "h-6 w-6",
  xl: "h-8 w-8",
}

/** Matches the phase-timeline running indicator (Lucide Loader + intent-active). */
export function Spinner({ size = "md", className }: SpinnerProps) {
  return (
    <Loader
      className={cn("animate-spin text-intent-active", SPINNER_SIZE[size], className)}
    />
  )
}

// ---------------------------------------------------------------------------
// EmptyState
// ---------------------------------------------------------------------------

interface EmptyStateProps {
  icon: LucideIcon
  heading: string
  sub?: string
  className?: string
  /** compact reduces vertical padding for dense data views */
  density?: "default" | "compact"
}

export function EmptyState({
  icon: Icon,
  heading,
  sub,
  className,
  density = "default",
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 text-center",
        density === "compact" ? "py-8" : "py-20",
        className,
      )}
    >
      <Icon className="h-10 w-10 text-border" />
      <p className="text-muted text-sm font-medium">{heading}</p>
      {sub && (
        <p className="text-muted text-xs max-w-xs leading-relaxed">{sub}</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FetchError
// ---------------------------------------------------------------------------

interface FetchErrorProps {
  message: string
  onRetry?: () => void
  className?: string
}

export function FetchError({ message, onRetry, className }: FetchErrorProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 text-xs text-intent-danger bg-intent-danger-subtle border border-intent-danger-border rounded-lg px-3 py-2.5",
        className,
      )}
    >
      <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button
          size="sm"
          variant="ghost"
          onClick={onRetry}
          className="h-5 px-2 text-[11px] text-intent-danger hover:text-intent-danger hover:bg-intent-danger-subtle shrink-0"
        >
          Retry
        </Button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// LoadingPane
// ---------------------------------------------------------------------------

interface LoadingPaneProps {
  message?: string
  className?: string
}

export function LoadingPane({ message, className }: LoadingPaneProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center h-48 gap-3",
        className,
      )}
    >
      <Spinner size="lg" />
      {message && <p className="text-xs text-muted">{message}</p>}
    </div>
  )
}
