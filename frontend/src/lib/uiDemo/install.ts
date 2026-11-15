import {
  DEMO_WORKFLOW_ID,
  demoConfigYaml,
  demoCostDashboard,
  demoEnvKeysStatus,
  demoHistoryEntries,
  demoHistoryRail,
  demoPrismaCounts,
  demoWorkflowEvents,
} from "./fixtures"

export const UI_DEMO_ENABLED = import.meta.env.VITE_UI_DEMO === "true"
export const STUB_LLM = UI_DEMO_ENABLED || import.meta.env.VITE_STUB_LLM === "true"

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function pathOf(input: RequestInfo | URL): string {
  const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url
  try {
    const url = new URL(raw, window.location.origin)
    return url.pathname + url.search
  } catch {
    return String(raw)
  }
}

function demoResponse(path: string, init?: RequestInit): Response | null {
  if (!path.startsWith("/api/")) return null

  if (path === "/api/config/env-keys/status") return jsonResponse(demoEnvKeysStatus)
  if (path === "/api/config/required-ui-keys") return jsonResponse(["fireworks", "gemini"])
  if (path === "/api/config/review") return jsonResponse({ content: demoConfigYaml })
  if (path === "/api/health") return jsonResponse({ ok: true, demo: true })

  if (path.startsWith("/api/history")) {
    const url = new URL(path, window.location.origin)
    if (url.searchParams.get("view") === "rail") {
      return jsonResponse(demoHistoryRail())
    }
    return jsonResponse(demoHistoryEntries())
  }

  const wfEvents = /^\/api\/workflow\/([^/]+)\/events$/.exec(path)
  if (wfEvents) {
    return jsonResponse({ events: demoWorkflowEvents(decodeURIComponent(wfEvents[1])) })
  }

  const runEvents = /^\/api\/run\/([^/]+)\/events$/.exec(path)
  if (runEvents) {
    const id = decodeURIComponent(runEvents[1])
    return jsonResponse({ events: demoWorkflowEvents(id) })
  }

  const prisma = /^\/api\/run\/([^/]+)\/prisma-counts$/.exec(path)
  if (prisma) {
    return jsonResponse(demoPrismaCounts(decodeURIComponent(prisma[1])))
  }

  const costs = /^\/api\/db\/([^/]+)\/costs\/dashboard$/.exec(path)
  if (costs) {
    return jsonResponse(demoCostDashboard())
  }

  if (path.match(/^\/api\/run\/[^/]+\/artifacts$/)) {
    return jsonResponse({ artifacts: ["manuscript.md", "prisma_flow.png", "submission.zip"] })
  }

  if (init?.method === "POST" && path === "/api/history/attach") {
    return jsonResponse({ run_id: DEMO_WORKFLOW_ID, topic: demoHistoryEntries()[0].topic })
  }

  const runConfig = /^\/api\/history\/([^/]+)\/config/.exec(path)
  if (runConfig) {
    return jsonResponse({ content: demoConfigYaml })
  }

  if (init?.method === "POST" && path === "/api/config/generate/stream") {
    const payload = `data: ${JSON.stringify({ type: "progress", step: "keywords" })}\n\ndata: ${JSON.stringify({ type: "done", yaml: demoConfigYaml })}\n\n`
    return new Response(payload, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    })
  }

  return null
}

export function installUiDemoFetch(): void {
  const nativeFetch = globalThis.fetch.bind(globalThis)
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = pathOf(input)
    const demo = demoResponse(path, init)
    if (demo) return demo
    return nativeFetch(input, init)
  }
}