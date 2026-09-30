import { useEffect, useRef, useState, type RefObject } from "react"
import type { LucideIcon } from "lucide-react"
import type { ResultsCategory } from "@/lib/resultsCategories"
import { GlassTabs } from "@/components/ui/glass-tabs"
import { cn } from "@/lib/utils"

export type { ResultsCategory } from "@/lib/resultsCategories"

export interface ResultsCategoryItem {
  id: ResultsCategory
  label: string
  icon: LucideIcon
}

interface ResultsCategoryNavProps {
  items: ResultsCategoryItem[]
  activeCategory: ResultsCategory
  onCategoryChange: (category: ResultsCategory) => void
}

/**
 * Below sm every tab gets an equal column with the icon stacked over an 11px label,
 * so all categories stay visible without horizontal scroll. Touch pointers get 44px targets.
 */
const PHONE_SEGMENTED = cn(
  "max-sm:grid max-sm:grid-flow-col max-sm:auto-cols-fr max-sm:gap-0.5 max-sm:overflow-visible max-sm:after:hidden",
  "max-sm:[&>[role=tab]]:min-w-0 max-sm:[&>[role=tab]]:min-h-11 max-sm:[&>[role=tab]]:flex-col max-sm:[&>[role=tab]]:justify-center",
  "max-sm:[&>[role=tab]]:gap-0.5 max-sm:[&>[role=tab]]:px-0 max-sm:[&>[role=tab]]:py-1 max-sm:[&>[role=tab]]:text-2xs max-sm:[&>[role=tab]]:tracking-tight",
  "max-sm:[&>[role=tab]>svg]:size-4 max-sm:[&>[role=tab]>span]:max-w-full max-sm:[&>[role=tab]>span]:truncate",
  "pointer-coarse:[&>[role=tab]]:min-h-11",
)

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const { overflowY } = getComputedStyle(node)
    if (overflowY === "auto" || overflowY === "scroll") return node
  }
  return null
}

/** True once the sticky element has scrolled up to its pinned offset. */
function useIsStuck(ref: RefObject<HTMLElement | null>, enabled: boolean): boolean {
  const [stuck, setStuck] = useState(false)
  useEffect(() => {
    const el = ref.current
    const scroller = el && enabled ? scrollParent(el) : null
    if (!el || !scroller) return
    const update = () => {
      const pinnedTop =
        scroller.getBoundingClientRect().top
        + parseFloat(getComputedStyle(scroller).paddingTop)
        + parseFloat(getComputedStyle(el).top)
      setStuck(scroller.scrollTop > 0 && el.getBoundingClientRect().top <= pinnedTop + 0.5)
    }
    const frame = requestAnimationFrame(update)
    scroller.addEventListener("scroll", update, { passive: true })
    return () => {
      cancelAnimationFrame(frame)
      scroller.removeEventListener("scroll", update)
    }
  }, [ref, enabled])
  return enabled && stuck
}

export function ResultsCategoryNav({
  items,
  activeCategory,
  onCategoryChange,
}: ResultsCategoryNavProps) {
  const ref = useRef<HTMLDivElement>(null)
  const pinned = activeCategory !== "manuscript"
  const stuck = useIsStuck(ref, pinned && items.length > 1)

  if (items.length <= 1) return null

  return (
    <div
      ref={ref}
      data-testid="results-category-nav"
      data-stuck={stuck || undefined}
      className={cn(
        pinned && [
          "sticky -top-3 z-20 -mx-6 -my-3 px-6 py-3",
          "before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-3 before:bg-background before:content-['']",
          "transition-[background-color,border-color,box-shadow] duration-150 motion-reduce:transition-none",
          stuck ? "glass-toolbar shadow-sm" : "bg-background border-b border-transparent",
        ],
      )}
    >
      <GlassTabs
        items={items}
        activeTab={activeCategory}
        onTabChange={onCategoryChange}
        className={PHONE_SEGMENTED}
      />
    </div>
  )
}
