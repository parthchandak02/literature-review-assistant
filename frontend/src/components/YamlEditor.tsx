import { useState, useMemo } from "react"
import { Pencil, Eye } from "lucide-react"
import hljs from "highlight.js/lib/core"
import yaml from "highlight.js/lib/languages/yaml"
import "highlight.js/styles/github-dark.css"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"

hljs.registerLanguage("yaml", yaml)

interface YamlEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  rows?: number
  className?: string
  isLoading?: boolean
  loadingLabel?: string
}

/**
 * YAML editor with syntax highlighting. Toggles between read-only highlighted
 * view and editable textarea. Uses highlight.js (github-dark theme).
 */
export function YamlEditor({
  value,
  onChange,
  placeholder = "Paste your review.yaml content here...",
  rows = 16,
  className = "",
  isLoading = false,
  loadingLabel = "Generating review YAML...",
}: YamlEditorProps) {
  const [editMode, setEditMode] = useState(false)
  const previewTokenStyle = `
    .yaml-preview-pre .hljs-literal { color: #f59e0b; }
    .yaml-preview-pre .hljs-number { color: #f97316; }
  `

  const highlighted = useMemo(() => {
    if (!value.trim()) return ""
    try {
      return hljs.highlight(value, { language: "yaml" }).value
    } catch {
      return value
    }
  }, [value])

  if (editMode && !isLoading) {
    return (
      <div className={`flex flex-col gap-2 ${className}`}>
        <style>{previewTokenStyle}</style>
        <div className="flex justify-end">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setEditMode(false)}
            className="text-muted hover:text-foreground text-xs gap-1.5"
          >
            <Eye className="h-3.5 w-3.5" />
            Preview
          </Button>
        </div>
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={rows}
          placeholder={placeholder}
          className="resize-none text-xs font-mono bg-background border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary leading-relaxed"
          spellCheck={false}
        />
      </div>
    )
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <style>{previewTokenStyle}</style>
      <div className="flex justify-end">
        {isLoading ? (
          <span className="text-xs text-muted">{loadingLabel}</span>
        ) : (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setEditMode(true)}
            className="text-muted hover:text-foreground text-xs gap-1.5"
          >
            <Pencil className="h-3.5 w-3.5" />
            Edit
          </Button>
        )}
      </div>
      <ScrollArea className="border border-border rounded-md bg-background h-[400px]">
        <pre className="hljs yaml-preview-pre text-xs p-4 font-mono leading-relaxed whitespace-pre-wrap min-h-full">
          {isLoading ? (
            <code className="text-muted">{loadingLabel}</code>
          ) : value.trim() ? (
            <code dangerouslySetInnerHTML={{ __html: highlighted }} />
          ) : (
            <code className="text-muted">{placeholder}</code>
          )}
        </pre>
      </ScrollArea>
    </div>
  )
}
