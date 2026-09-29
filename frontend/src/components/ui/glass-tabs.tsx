import { useCallback, useEffect, useRef, type KeyboardEvent } from "react"
import { useEdgeFade } from "@/hooks/useEdgeFade"
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

const SCROLL_INSET = 24

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
  const listRef = useRef<HTMLDivElement | null>(null)
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])
  const activeIndex = items.findIndex((item) => item.id === activeTab)
  const focusableIndex = activeIndex >= 0 ? activeIndex : 0
  const fadeStyle = useEdgeFade(listRef)

  const scrollActiveIntoView = useCallback(() => {
    const list = listRef.current
    const tab = activeIndex >= 0 ? tabRefs.current[activeIndex] : null
    if (!list || !tab || list.scrollWidth <= list.clientWidth) return
    const listLeft = list.getBoundingClientRect().left
    const startOf = (el: HTMLElement) => el.getBoundingClientRect().left - listLeft + list.scrollLeft
    const start = startOf(tab)
    const end = start + tab.offsetWidth
    let target = list.scrollLeft
    if (start < target + SCROLL_INSET) target = start - SCROLL_INSET
    else if (end > target + list.clientWidth - SCROLL_INSET) target = end - list.clientWidth + SCROLL_INSET
    const cut = tabRefs.current.find((el) => el && startOf(el) < target && startOf(el) + el.offsetWidth > target)
    if (cut && cut !== tab) {
      const cutEnd = startOf(cut) + cut.offsetWidth
      if (end <= cutEnd + list.clientWidth) target = cutEnd
    }
    list.scrollLeft = Math.max(0, target)
  }, [activeIndex])

  useEffect(() => {
    scrollActiveIntoView()
    const list = listRef.current
    if (!list) return
    // Layout can shift after mount (fonts, sidebar); keep the active tab visible when it does.
    let active = true
    void document.fonts?.ready.then(() => {
      if (active) scrollActiveIntoView()
    })
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => scrollActiveIntoView()) : null
    observer?.observe(list)
    return () => {
      active = false
      observer?.disconnect()
    }
  }, [scrollActiveIntoView, items.length])

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
      ref={listRef}
      style={fadeStyle}
      role="tablist"
      aria-orientation="horizontal"
      onKeyDown={handleKeyDown}
      className={cn(
        "items-center overflow-x-auto scrollbar-none",
        underline ? "gap-3 border-b border-border sm:gap-4" : "gap-2",
        equalWidth && !underline
          ? "flex sm:grid sm:grid-flow-col sm:auto-cols-fr sm:w-full"
          : "flex after:block after:w-6 after:shrink-0 after:content-['']",
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
            {Icon && <Icon className={cn("h-3.5 w-3.5", underline && "max-sm:hidden")} aria-hidden />}
            <span>{item.label}</span>
          </button>
        )
      })}
    </div>
  )
}
