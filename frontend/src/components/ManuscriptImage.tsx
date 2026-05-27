import { useState } from "react"

/** Markdown figure: hide on 404/missing file instead of spamming the network console. */
export function ManuscriptImage({ src, alt }: { src?: string; alt?: string }) {
  const [failed, setFailed] = useState(false)
  if (failed || !src) return null
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
