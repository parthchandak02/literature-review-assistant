import { BarChart3, Table2 } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  costOpsSegmentButtonClass,
  costOpsSegmentGroupClass,
} from "./costOpsFormatters"

export type ChartTableMode = "chart" | "table"

export interface SegmentOption<T extends string> {
  value: T
  label: string
  icon?: React.ElementType
}

export interface SegmentedControlProps<T extends string> {
  value: T
  options: readonly SegmentOption<T>[]
  onChange: (value: T) => void
  ariaLabel: string
  className?: string
  children?: React.ReactNode
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
  children,
}: SegmentedControlProps<T>) {
  return (
    <div role="group" aria-label={ariaLabel} className={cn(costOpsSegmentGroupClass, className)}>
      {options.map(({ value: optionValue, label, icon: Icon }) => (
        <button
          key={optionValue}
          type="button"
          className={costOpsSegmentButtonClass(value === optionValue)}
          onClick={() => onChange(optionValue)}
          aria-pressed={value === optionValue}
        >
          {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
          {label}
        </button>
      ))}
      {children}
    </div>
  )
}

const CHART_TABLE_OPTIONS: readonly SegmentOption<ChartTableMode>[] = [
  { value: "chart", label: "Chart", icon: BarChart3 },
  { value: "table", label: "Table", icon: Table2 },
]

export interface ChartTableToggleProps {
  mode: ChartTableMode
  onChange: (mode: ChartTableMode) => void
  ariaLabel?: string
  className?: string
  children?: React.ReactNode
}

export function ChartTableToggle({
  mode,
  onChange,
  ariaLabel = "Display as",
  className,
  children,
}: ChartTableToggleProps) {
  return (
    <SegmentedControl
      value={mode}
      options={CHART_TABLE_OPTIONS}
      onChange={onChange}
      ariaLabel={ariaLabel}
      className={className}
    >
      {children}
    </SegmentedControl>
  )
}
