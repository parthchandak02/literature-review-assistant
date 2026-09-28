/**
 * Shared feedback components used across multiple views.
 *
 * Spinner     - inline animated spinner with size variants
 * EmptyState  - centred icon + heading + optional sub-text
 * FetchError  - red alert box with optional Retry and Dismiss actions
 * LoadingPane - centred spinner for full-pane loading states
 */
import { AlertTriangle, Loader, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
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
  action?: ReactNode
}

export function EmptyState({
  icon: Icon,
  heading,
  sub,
  className,
  density = "default",
  action,
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
      {action}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FetchError
// ---------------------------------------------------------------------------

interface FetchErrorProps {
  message: string
  /** Re-runs the failed request. Renders a "Retry" button. */
  onRetry?: () => void
  /** Clears the error without refetching. Renders a "Dismiss" button. */
  onDismiss?: () => void
  className?: string
}

const FETCH_ERROR_ACTION_CLASS =
  "text-intent-danger-text hover:text-intent-danger-text hover:bg-intent-danger-subtle shrink-0"

export function FetchError({ message, onRetry, onDismiss, className }: FetchErrorProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-2 text-xs text-intent-danger-text bg-intent-danger-subtle border border-intent-danger-border rounded-lg px-3 py-2.5",
        className,
      )}
    >
      <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-intent-danger" aria-hidden />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <Button type="button" size="xs" variant="ghost" onClick={onRetry} className={FETCH_ERROR_ACTION_CLASS}>
          Retry
        </Button>
      )}
      {onDismiss && (
        <Button type="button" size="xs" variant="ghost" onClick={onDismiss} className={FETCH_ERROR_ACTION_CLASS}>
          <X aria-hidden />
          Dismiss
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
