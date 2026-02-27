/**
 * Shared section layout primitives.
 *
 * CollapsibleSection -- card surface with a toggle-able header and animated body.
 * PageSection        -- card surface with a static titled header and optional action slot.
 *
 * Both use the canonical `.card-surface` and `.section-trigger` CSS utilities from
 * index.css so the visual language stays consistent across all views.
 */
import { useState } from "react"
import { ChevronDown, ChevronUp } from "lucide-react"
import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"

// ---------------------------------------------------------------------------
// CollapsibleSection
// ---------------------------------------------------------------------------

interface CollapsibleSectionProps {
  /** Icon shown left of the title. */
  icon?: LucideIcon
  title: string
  /** Optional badge / chip rendered right of the title. */
  badge?: React.ReactNode
  /** Optional description rendered right of the title (muted text). */
  description?: string
  /** Controls initial open state. Defaults to false. */
  defaultOpen?: boolean
  /** Override open state externally (controlled mode). */
  open?: boolean
  /** Called when the header is clicked in controlled mode. */
  onToggle?: () => void
  children: React.ReactNode
  className?: string
}

export function CollapsibleSection({
  icon: Icon,
  title,
  badge,
  description,
  defaultOpen = false,
  open: controlledOpen,
  onToggle,
  children,
  className,
}: CollapsibleSectionProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen)
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : internalOpen

  function handleToggle() {
    if (isControlled) {
      onToggle?.()
    } else {
      setInternalOpen((v) => !v)
    }
  }

  return (
    <div className={cn("card-surface overflow-hidden", className)}>
      <button onClick={handleToggle} className="section-trigger">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && <Icon className="h-4 w-4 text-zinc-500 shrink-0" />}
          <span className="text-sm font-medium text-zinc-300 shrink-0">{title}</span>
          {badge}
          {description && (
            <span className="label-muted truncate">{description}</span>
          )}
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-zinc-600 shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 text-zinc-600 shrink-0" />
        )}
      </button>

      {open && (
        <div className="border-t border-zinc-800">
          {children}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PageSection
// ---------------------------------------------------------------------------

interface PageSectionProps {
  /** Icon shown left of the title. */
  icon?: LucideIcon
  title: string
  /** Optional muted description shown right of the title in the header. */
  description?: string
  /** Optional element placed on the right side of the header (e.g. a Button). */
  action?: React.ReactNode
  children: React.ReactNode
  /** Extra classes on the outer card wrapper. */
  className?: string
  /** Extra classes on the inner content wrapper. */
  contentClassName?: string
}

export function PageSection({
  icon: Icon,
  title,
  description,
  action,
  children,
  className,
  contentClassName,
}: PageSectionProps) {
  return (
    <div className={cn("card-surface overflow-hidden", className)}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && <Icon className="h-4 w-4 text-zinc-500 shrink-0" />}
          <span className="text-sm font-medium text-zinc-300 shrink-0">{title}</span>
          {description && <span className="label-muted truncate">{description}</span>}
        </div>
        {action && <div>{action}</div>}
      </div>
      <div className={cn("p-4", contentClassName)}>{children}</div>
    </div>
  )
}
