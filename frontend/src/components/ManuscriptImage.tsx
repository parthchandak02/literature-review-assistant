import { useState } from "react"
import { ImageOff } from "lucide-react"

export function ManuscriptImage({ src, alt }: { src?: string; alt?: string }) {
  const [failed, setFailed] = useState(false)
  if (failed || !src) {
    const name = alt || "untitled figure"
    return (
      <span
        role="img"
        aria-label={`Figure not found: ${name}`}
        className="not-prose my-4 flex items-center justify-center gap-2 rounded-panel border border-dashed border-intent-warning-border bg-intent-warning-subtle px-4 py-6 text-sm text-intent-warning-text"
      >
        <ImageOff className="h-4 w-4 shrink-0" aria-hidden />
        <span>Figure not found: {name}</span>
      </span>
    )
  }
  return (
    <img
      src={src}
      alt={alt ?? ""}
      className="max-w-full rounded border border-border my-4 mx-auto block"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}
