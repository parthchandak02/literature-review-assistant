import { Columns3, Download } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { PAPER_COLUMNS, type PaperColumnId } from "./paperColumns"

export interface ColumnsMenuProps {
  visible: Set<PaperColumnId>
  empty: Set<PaperColumnId>
  onToggle: (id: PaperColumnId, visible: boolean) => void
  onReset: () => void
}

export function ColumnsMenu({ visible, empty, onToggle, onReset }: ColumnsMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="secondary" size="xs">
          <Columns3 />
          Columns
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Show columns</DropdownMenuLabel>
        {PAPER_COLUMNS.map(({ id, label }) => (
          <DropdownMenuCheckboxItem
            key={id}
            checked={visible.has(id)}
            onSelect={(e) => e.preventDefault()}
            onCheckedChange={(checked) => onToggle(id, checked === true)}
            className="text-xs"
          >
            <span className="flex-1">{label}</span>
            {empty.has(id) && <span className="text-2xs text-muted">empty</span>}
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onReset} className="text-xs">
          Auto (hide empty columns)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export interface ExportMenuProps {
  csvUrl: string
  risUrl: string
  total: number
}

export function ExportMenu({ csvUrl, risUrl, total }: ExportMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="secondary" size="xs" disabled={total === 0}>
          <Download />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel>
          Export {total.toLocaleString()} {total === 1 ? "paper" : "papers"}
        </DropdownMenuLabel>
        <DropdownMenuItem asChild className="text-xs">
          <a href={csvUrl} download>
            CSV (spreadsheet)
          </a>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="text-xs">
          <a href={risUrl} download>
            RIS (Zotero, EndNote, Rayyan)
          </a>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
