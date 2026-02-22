/**
 * Shared feedback components used across multiple views.
 *
 * Spinner     - inline animated spinner with size variants
 * EmptyState  - centred icon + heading + optional sub-text
 * FetchError  - red alert box with optional retry button
 * LoadingPane - centred spinner for full-pane loading states
 */
import { AlertTriangle, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

// ---------------------------------------------------------------------------
// Spinner
// ---------------------------------------------------------------------------

interface SpinnerProps {
  /** "sm" = 16px, "md" = 20px (default), "lg" = 32px */
  size?: "sm" | "md" | "lg"
  className?: string
}

const SPINNER_SIZE: Record<string, string> = {
  sm: "h-4 w-4",
  md: "h-5 w-5",
  lg: "h-8 w-8",
}

export function Spinner({ size = "md", className }: SpinnerProps) {
  return (
    <Loader2
      className={cn("animate-spin text-zinc-500", SPINNER_SIZE[size], className)}
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
}

export function EmptyState({ icon: Icon, heading, sub, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-20 gap-3 text-center",
        className,
      )}
    >
      <Icon className="h-10 w-10 text-zinc-700" />
      <p className="text-zinc-400 text-sm font-medium">{heading}</p>
      {sub && (
        <p className="text-zinc-600 text-xs max-w-xs leading-relaxed">{sub}</p>
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
        "flex items-start gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5",
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
          className="h-5 px-2 text-[11px] text-red-400 hover:text-red-300 hover:bg-red-500/10 shrink-0"
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
      <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
      {message && <p className="text-xs text-zinc-500">{message}</p>}
    </div>
  )
}
