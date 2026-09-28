import type { HistoryEntry } from "@/lib/api"

/** `config_generating` rows have no saved review.yaml yet; every other status may. */
export function reusableConfigRuns(history: HistoryEntry[]): HistoryEntry[] {
  return history.filter((entry) => entry.status !== "config_generating")
}
