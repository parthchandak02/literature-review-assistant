import { ViewToolbar } from "@/components/ui/view-toolbar"

export function ScreeningSummaryHeader() {
  return (
    <ViewToolbar
      bordered={false}
      className="!h-auto px-0"
      title={
        <div>
          <h2 className="text-base font-semibold text-foreground">Human Review Checkpoint</h2>
          <p className="text-sm text-muted mt-0.5 font-normal">
            The workflow has paused for human review. Inspect the AI screening decisions below,
            then approve to continue with extraction.
          </p>
        </div>
      }
    />
  )
}
