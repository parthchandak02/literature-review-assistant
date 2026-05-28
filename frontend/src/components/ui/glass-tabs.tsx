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
  className?: string
}

function accentClasses(accent: "violet" | "amber", active: boolean): string {
  if (accent === "amber") {
    return active
      ? "border-intent-warning/70 bg-intent-warning-subtle text-intent-warning"
      : "border-border/80 text-muted hover:text-intent-warning hover:border-intent-warning/40 hover:bg-intent-warning-subtle"
  }
  return active
    ? "border-intent-primary/70 bg-intent-primary-subtle text-foreground"
    : "border-border/80 text-muted hover:text-foreground hover:border-intent-primary/40 hover:bg-surface-2/55"
}

export function GlassTabs<T extends string>({
  items,
  activeTab,
  onTabChange,
  equalWidth = false,
  className,
}: GlassTabsProps<T>) {
  return (
    <div
      role="tablist"
      className={cn(
        "items-center gap-2 overflow-x-auto scrollbar-none",
        equalWidth
          ? "flex sm:grid sm:grid-flow-col sm:auto-cols-fr sm:w-full"
          : "flex",
        className,
      )}
    >
      {items.map((item) => {
        const active = item.id === activeTab
        const Icon = item.icon
        const accent = item.accent ?? "violet"
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            id={`tab-${item.id}`}
            aria-controls={`tabpanel-${item.id}`}
            onClick={() => onTabChange(item.id)}
            className={cn(
              "glass-interactive inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium whitespace-nowrap shrink-0 transition-colors",
              equalWidth
                ? "min-w-[8.5rem] justify-center sm:min-w-0 sm:w-full"
                : "",
              accentClasses(accent, active),
            )}
          >
            {Icon && <Icon className="h-3.5 w-3.5" />}
            <span>{item.label}</span>
          </button>
        )
      })}
    </div>
  )
}
