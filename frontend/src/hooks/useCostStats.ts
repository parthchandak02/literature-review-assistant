import { useMemo } from "react"
import type { ReviewEvent } from "@/lib/api"

export interface ModelStat {
  model: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
}

export interface PhaseStat {
  phase: string
  cost_usd: number
  calls: number
}

export interface CostStats {
  total_cost: number
  total_tokens_in: number
  total_tokens_out: number
  total_calls: number
  by_model: ModelStat[]
  by_phase: PhaseStat[]
}

export function useCostStats(events: ReviewEvent[]): CostStats {
  return useMemo(() => {
    const modelMap: Record<string, ModelStat> = {}
    const phaseMap: Record<string, PhaseStat> = {}
    let total_cost = 0
    let total_tokens_in = 0
    let total_tokens_out = 0
    let total_calls = 0

    for (const ev of events) {
      if (ev.type !== "api_call" || ev.status !== "success") continue
      const cost = ev.cost_usd ?? 0
      const tin = ev.tokens_in ?? 0
      const tout = ev.tokens_out ?? 0
      const model = ev.model ?? "unknown"
      const phase = ev.phase ?? "unknown"

      total_cost += cost
      total_tokens_in += tin
      total_tokens_out += tout
      total_calls += 1

      if (!modelMap[model]) {
        modelMap[model] = { model, calls: 0, tokens_in: 0, tokens_out: 0, cost_usd: 0 }
      }
      modelMap[model].calls += 1
      modelMap[model].tokens_in += tin
      modelMap[model].tokens_out += tout
      modelMap[model].cost_usd += cost

      if (!phaseMap[phase]) {
        phaseMap[phase] = { phase, cost_usd: 0, calls: 0 }
      }
      phaseMap[phase].cost_usd += cost
      phaseMap[phase].calls += 1
    }

    const by_model = Object.values(modelMap).sort((a, b) => b.cost_usd - a.cost_usd)
    const by_phase = Object.values(phaseMap).sort((a, b) => b.cost_usd - a.cost_usd)

    return { total_cost, total_tokens_in, total_tokens_out, total_calls, by_model, by_phase }
  }, [events])
}
