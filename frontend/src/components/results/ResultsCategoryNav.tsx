import type { LucideIcon } from "lucide-react"
import type { ResultsCategory } from "@/lib/resultsCategories"
import { GlassTabs } from "@/components/ui/glass-tabs"

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

export function ResultsCategoryNav({
  items,
  activeCategory,
  onCategoryChange,
}: ResultsCategoryNavProps) {
  if (items.length <= 1) return null

  return (
    <GlassTabs
      items={items}
      activeTab={activeCategory}
      onTabChange={onCategoryChange}
      className="pb-1"
    />
  )
}
