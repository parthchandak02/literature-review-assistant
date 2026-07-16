import { useQuery } from "@tanstack/react-query"
import { fetchHistory } from "@/lib/api"

export const HISTORY_REFRESH_MS = 30_000

export function historyQueryKey(runRoot = "runs") {
  return ["history", runRoot] as const
}

export function useHistory(options?: { enabled?: boolean; refetchInterval?: number | false }) {
  return useQuery({
    queryKey: historyQueryKey(),
    queryFn: () => fetchHistory(),
    enabled: options?.enabled ?? true,
    refetchInterval: options?.refetchInterval ?? HISTORY_REFRESH_MS,
    refetchIntervalInBackground: false,
  })
}

export function historyFetchErrorMessage(error: unknown): string | null {
  const msg = error instanceof Error ? error.message : String(error)
  return msg.toLowerCase().includes("fetch") ? "Cannot reach backend" : msg
}
