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
          "sticky -top-3 z-20 -mx-6 -my-3 bg-background px-6 py-3 border-b border-transparent",
          "before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-3 before:bg-background before:content-['']",
          "transition-[border-color,box-shadow] duration-150 motion-reduce:transition-none",
          "data-[stuck]:border-border data-[stuck]:shadow-sm",
        ],
      )}
    >
      <GlassTabs items={items} activeTab={activeCategory} onTabChange={onCategoryChange} />
    </div>
  )
}
