import { useQuery } from "@tanstack/react-query"
import { fetchPapersReference } from "@/lib/api"

export function referencesQueryKey(runId: string, workflowId?: string | null) {
  return ["references", runId, workflowId ?? ""] as const
}

export function useReferences(
  runId: string,
  workflowId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(runId)
  return useQuery({
    queryKey: referencesQueryKey(runId, workflowId),
    queryFn: () => fetchPapersReference(runId, workflowId),
    enabled,
    staleTime: 30_000,
  })
}
