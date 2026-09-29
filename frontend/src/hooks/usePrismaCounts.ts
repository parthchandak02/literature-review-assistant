import { useQuery } from "@tanstack/react-query"
import { fetchPrismaCounts } from "@/lib/api"

export function prismaCountsQueryKey(runId: string) {
  return ["prisma-counts", runId] as const
}

/** Backend PRISMA counts + sidecar staleness for a run (GET /api/run/{run_id}/prisma-counts). */
export function usePrismaCounts(runId: string | null | undefined, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: prismaCountsQueryKey(runId ?? ""),
    queryFn: () => fetchPrismaCounts(runId as string),
    enabled: (options?.enabled ?? true) && Boolean(runId),
    staleTime: 30_000,
  })
}
