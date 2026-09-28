import { useId, useMemo, useState } from "react"
import { AlertTriangle, Eye, Pencil, RotateCcw } from "lucide-react"
import hljs from "highlight.js/lib/core"
import yaml from "highlight.js/lib/languages/yaml"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { YamlIssue } from "@/lib/reviewYaml"
import { cn } from "@/lib/utils"

hljs.registerLanguage("yaml", yaml)

interface YamlEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  isLoading?: boolean
  loadingLabel?: string
  ariaLabel?: string
  dirty?: boolean
  onReset?: () => void
  resetLabel?: string
  error?: YamlIssue | null
}

/**
 * YAML editor with syntax highlighting. Toggles between read-only highlighted
 * view and editable textarea. Syntax colors from styles/hljs-theme.css.
 */
export function YamlEditor({
  value,
  onChange,
  placeholder = "Paste your review.yaml content here...",
  className = "",
  isLoading = false,
  loadingLabel = "Generating review YAML...",
  ariaLabel = "Review config YAML",
  dirty = false,
  onReset,
  resetLabel = "Reset to generated",
  error = null,
}: YamlEditorProps) {
  const [editMode, setEditMode] = useState(false)
  const errorId = useId()

  const highlighted = useMemo(() => {
    if (!value.trim()) return ""
    try {
      return hljs.highlight(value, { language: "yaml" }).value
    } catch {
      return value
    }
  }, [value])

  const editing = editMode && !isLoading

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center justify-end gap-2">
        {dirty && !isLoading && (
          <span className="mr-auto inline-flex items-center gap-1.5 text-xs text-muted" role="status">
            <span className="h-1.5 w-1.5 rounded-full bg-intent-warning" aria-hidden />
            Unsaved edits
          </span>
        )}
        {isLoading ? (
          <span className="text-xs text-muted">{loadingLabel}</span>
        ) : (
          <>
            {dirty && onReset && (
              <Button type="button" variant="ghost" size="xs" onClick={onReset} className="text-muted hover:text-foreground">
                <RotateCcw />
                {resetLabel}
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="xs"
              onClick={() => setEditMode((v) => !v)}
              className="text-muted hover:text-foreground"
            >
              {editing ? <Eye /> : <Pencil />}
              {editing ? "Preview" : "Edit"}
            </Button>
          </>
        )}
      </div>
      {editing ? (
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-label={ariaLabel}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          className="h-[60vh] min-h-64 resize-y text-xs font-mono bg-background border-border text-foreground placeholder:text-muted focus-visible:ring-intent-primary leading-relaxed"
          spellCheck={false}
        />
      ) : (
        <ScrollArea
          className="border border-border rounded-md bg-background h-[60vh] min-h-64"
          aria-label={ariaLabel}
        >
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
      )}
      {error && !isLoading && (
        <p
          id={errorId}
          role="alert"
          className="flex items-start gap-1.5 rounded-md border border-intent-danger-border bg-intent-danger-subtle px-3 py-2 text-xs text-intent-danger-text"
        >
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden />
          <span>
            {error.line !== null ? `YAML error on line ${error.line}: ` : "YAML error: "}
            {error.message}
          </span>
        </p>
      )}
    </div>
  )
}
