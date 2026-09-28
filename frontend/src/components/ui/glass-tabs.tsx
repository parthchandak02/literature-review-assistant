import { useRef, type KeyboardEvent } from "react"
import { cn } from "@/lib/utils"

interface GlassTabItem<T extends string> {
  id: T
  label: string
  icon?: React.ElementType
  accent?: "violet" | "amber"
}

interface GlassTabsProps<T extends string> {
  items: GlassTabItem<T>[]
  activeTab: T
  onTabChange: (tab: T) => void
  equalWidth?: boolean
  /** "pill" (default) bordered glass tabs; "underline" compact content-width tabs. */
  variant?: "pill" | "underline"
  className?: string
}

const FOCUS_RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"

function accentClasses(accent: "violet" | "amber", active: boolean): string {
  if (accent === "amber") {
    return active
      ? "border-intent-warning/70 bg-intent-warning-subtle text-intent-warning-text"
      : "border-border/80 text-muted hover:text-intent-warning hover:border-intent-warning/40 hover:bg-intent-warning-subtle"
  }
  return active
    ? "border-intent-primary/70 bg-intent-primary-subtle text-foreground"
    : "border-border/80 text-muted hover:text-foreground hover:border-intent-primary/40 hover:bg-surface-2/55"
}

function underlineAccentClasses(accent: "violet" | "amber", active: boolean): string {
  if (accent === "amber") {
    return active
      ? "border-intent-warning text-intent-warning-text"
      : "border-transparent text-muted hover:text-intent-warning-text hover:border-intent-warning/40"
  }
  return active
    ? "border-intent-primary text-foreground"
    : "border-transparent text-muted hover:text-foreground hover:border-border-strong"
}

export function GlassTabs<T extends string>({
  items,
  activeTab,
  onTabChange,
  equalWidth = false,
  variant = "pill",
  className,
}: GlassTabsProps<T>) {
  const underline = variant === "underline"
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const activeIndex = items.findIndex((item) => item.id === activeTab)
  const focusableIndex = activeIndex >= 0 ? activeIndex : 0

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (items.length === 0) return
    const current = tabRefs.current.findIndex((el) => el === document.activeElement)
    const from = current >= 0 ? current : focusableIndex
    let next: number
    switch (event.key) {
      case "ArrowRight":
        next = (from + 1) % items.length
        break
      case "ArrowLeft":
        next = (from - 1 + items.length) % items.length
        break
      case "Home":
        next = 0
        break
      case "End":
        next = items.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    tabRefs.current[next]?.focus()
    onTabChange(items[next].id)
  }

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      onKeyDown={handleKeyDown}
      className={cn(
        "items-center overflow-x-auto scrollbar-none",
        underline ? "gap-4 border-b border-border" : "gap-2",
        equalWidth && !underline
          ? "flex sm:grid sm:grid-flow-col sm:auto-cols-fr sm:w-full"
          : "flex",
        className,
      )}
    >
      {items.map((item, index) => {
        const active = item.id === activeTab
        const Icon = item.icon
        const accent = item.accent ?? "violet"
        return (
          <button
            key={item.id}
            ref={(el) => {
              tabRefs.current[index] = el
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={index === focusableIndex ? 0 : -1}
            id={`tab-${item.id}`}
            aria-controls={`tabpanel-${item.id}`}
            onClick={() => onTabChange(item.id)}
            className={cn(
              "inline-flex items-center gap-1.5 text-sm font-medium whitespace-nowrap shrink-0 transition-colors",
              FOCUS_RING,
              underline
                ? cn(
                    "-mb-px rounded-t-control border-b-2 px-1 py-2",
                    underlineAccentClasses(accent, active),
                  )
                : cn(
                    "glass-interactive rounded-control border px-3 py-2",
                    equalWidth ? "min-w-[8.5rem] justify-center sm:min-w-0 sm:w-full" : "",
                    accentClasses(accent, active),
                  ),
            )}
          >
            {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
            <span>{item.label}</span>
          </button>
        )
      })}
    </div>
  )
}
