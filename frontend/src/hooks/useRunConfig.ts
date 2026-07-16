import { useQuery } from "@tanstack/react-query"
import { fetchRunConfig, getDefaultReviewConfig } from "@/lib/api"

export function runConfigQueryKey(workflowId: string) {
  return ["runConfig", workflowId] as const
}

export function defaultReviewConfigQueryKey() {
  return ["defaultReviewConfig"] as const
}

export function useRunConfig(
  workflowId: string | null | undefined,
  options?: { enabled?: boolean },
) {
  const enabled = (options?.enabled ?? true) && Boolean(workflowId)
  return useQuery({
    queryKey: runConfigQueryKey(workflowId ?? ""),
    queryFn: () => fetchRunConfig(workflowId!),
    enabled,
    retry: false,
  })
}

export function useDefaultReviewConfig(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: defaultReviewConfigQueryKey(),
    queryFn: () => getDefaultReviewConfig(),
    enabled: options?.enabled ?? true,
  })
}
