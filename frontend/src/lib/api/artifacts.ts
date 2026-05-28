import { downloadUrl } from "./urls"

/** Fetch artifact file contents as plain text (e.g. manuscript markdown). */
export async function fetchArtifactText(path: string, signal?: AbortSignal): Promise<string> {
  const res = await fetch(downloadUrl(path), { signal })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.text()
}
