import { Filter } from "lucide-react"
import { EmptyState } from "@/components/ui/feedback"
import { ScreeningPaperRow } from "./ScreeningPaperRow"
import type { HumanDecision, OverrideMap, ScreeningRowData } from "./screeningModel"

export interface ScreeningPaperListProps {
  rows: ScreeningRowData[]
  overrides: OverrideMap
  focusedKey: string | null
  expanded: ReadonlySet<string>
  selected: ReadonlySet<string>
  onDecide: (key: string, decision: HumanDecision) => void
  onClearOverride: (key: string) => void
  onReasonChange: (key: string, reason: string) => void
  onToggleExpanded: (key: string) => void
  onToggleSelected: (key: string) => void
  onFocusRow: (key: string) => void
  readOnly?: boolean
}

export function ScreeningPaperList({
  rows,
  overrides,
  focusedKey,
  expanded,
  selected,
  ...rest
}: ScreeningPaperListProps) {
  if (rows.length === 0) {
    return <EmptyState icon={Filter} heading="No papers match these filters." className="py-8" />
  }

  const activeKey = focusedKey && rows.some((r) => r.key === focusedKey) ? focusedKey : rows[0].key

  return (
    <div
      role="grid"
      aria-label="Screened papers"
      aria-multiselectable={!rest.readOnly}
      aria-readonly={rest.readOnly || undefined}
      aria-rowcount={rows.length}
      className="glass-table-shell divide-y"
    >
      {rows.map((row) => (
        <ScreeningPaperRow
          key={row.key}
          row={row}
          override={overrides.get(row.key) ?? null}
          focused={row.key === activeKey}
          expanded={expanded.has(row.key)}
          selected={selected.has(row.key)}
          {...rest}
        />
      ))}
    </div>
  )
}
