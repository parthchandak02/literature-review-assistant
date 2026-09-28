import { ConfirmDialog } from "@/components/ConfirmDialog"
import { templateTextWarning } from "./draftQuality"
import type { PackagePrompt } from "./submissionPackage"

const OVERWRITE_TEXT =
  "This regenerates the .tex, DOCX and references from the current manuscript and overwrites the existing package ZIP."

export function PackageBuildConfirm({
  prompt,
  onConfirm,
  onCancel,
}: {
  prompt: PackagePrompt | null
  onConfirm: () => void
  onCancel: () => void
}) {
  const sections = prompt?.sections ?? []
  const hasTemplateText = sections.length > 0
  const overwrite = Boolean(prompt?.overwrite)
  const description = [overwrite ? OVERWRITE_TEXT : null, hasTemplateText ? templateTextWarning(sections) : null]
    .filter(Boolean)
    .join(" ")

  return (
    <ConfirmDialog
      open={prompt != null}
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
      title={
        hasTemplateText
          ? "Manuscript still has template text"
          : "Rebuild submission package?"
      }
      description={description}
      confirmLabel={hasTemplateText ? "Package anyway" : "Rebuild"}
      cancelLabel="Cancel"
      confirmVariant="default"
      onConfirm={onConfirm}
    />
  )
}
