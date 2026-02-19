import { ResultsPanel } from "@/components/ResultsPanel"
import { FileText, Lock } from "lucide-react"

interface ResultsViewProps {
  outputs: Record<string, unknown>
  isDone: boolean
}

export function ResultsView({ outputs, isDone }: ResultsViewProps) {
  if (!isDone) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
        <Lock className="h-10 w-10 text-zinc-700" />
        <p className="text-zinc-500 text-sm">Results will be available once the review completes.</p>
      </div>
    )
  }

  if (Object.keys(outputs).length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-center">
        <FileText className="h-10 w-10 text-zinc-700" />
        <p className="text-zinc-500 text-sm">No output files found.</p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl">
      <ResultsPanel outputs={outputs} />
    </div>
  )
}
