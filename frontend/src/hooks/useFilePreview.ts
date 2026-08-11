import { useCallback, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchArtifactText } from "@/lib/api"
import {
  isPreviewableFile,
  resolveFileUrl,
  type OutputFile,
} from "@/components/results/artifactFileUtils"

async function loadPreviewText(file: OutputFile, signal: AbortSignal): Promise<string> {
  const url = resolveFileUrl(file.path)
  if (url.startsWith("/api/")) {
    const res = await fetch(url, { signal })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.text()
  }
  return fetchArtifactText(file.path, signal)
}

export function useFilePreview(file: OutputFile | null) {
  const previewable = Boolean(file && isPreviewableFile(file))
  const [retryToken, setRetryToken] = useState(0)
  const retry = useCallback(() => setRetryToken((t) => t + 1), [])

  const query = useQuery({
    queryKey: ["filePreview", file?.key, file?.path, retryToken] as const,
    enabled: previewable && file != null,
    queryFn: ({ signal }) => loadPreviewText(file!, signal),
    staleTime: 30_000,
  })

  return {
    content: previewable ? (query.data ?? null) : null,
    loading: previewable ? query.isFetching : false,
    error: previewable ? query.isError : false,
    retry,
    isPreviewable: previewable,
  }
}

export function useFileTextPreview(path: string | null) {
  const activePath = path?.trim() ? path : null
  const [retryToken, setRetryToken] = useState(0)
  const retry = useCallback(() => setRetryToken((t) => t + 1), [])

  const query = useQuery({
    queryKey: ["fileTextPreview", activePath, retryToken] as const,
    enabled: activePath != null,
    queryFn: ({ signal }) => fetchArtifactText(activePath!, signal),
    staleTime: 30_000,
  })

  return {
    content: activePath ? (query.data ?? null) : null,
    loading: activePath ? query.isFetching : false,
    error: activePath && query.isError ? (query.error instanceof Error ? query.error.message : String(query.error)) : null,
    retry,
  }
}
