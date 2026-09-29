import { parseDate } from "@/lib/format"

export const CONFIG_GENERATING_STALL_MS = 60 * 60 * 1000

/** Label shown in the sidebar card, run header and Config tab for a stalled config generation. */
export const CONFIG_STALLED_LABEL = "Stalled"

export interface ConfigStallInput {
  status?: string | null
  live_run_id?: string | null
  created_at?: string | null
  updated_at?: string | null
}

/** A `config_generating` run with no live stream whose last update is over an hour old. */
export function isConfigGenerationStalled(
  entry: ConfigStallInput,
  hasLiveStream: boolean,
  now: number = Date.now(),
): boolean {
  if ((entry.status ?? "").trim().toLowerCase() !== "config_generating") return false
  if (hasLiveStream || entry.live_run_id) return false
  const stamp = entry.updated_at || entry.created_at
  if (!stamp) return false
  const since = parseDate(stamp).getTime()
  return Number.isFinite(since) && now - since > CONFIG_GENERATING_STALL_MS
}
