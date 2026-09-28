// @vitest-environment jsdom
import "@/test/dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { ResultsView } from "./ResultsView"

function withQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>
}

describe("ResultsView locked state", () => {
  it("navigates to Activity from the locked state", async () => {
    const user = userEvent.setup()
    const onOpenActivity = vi.fn()
    render(
      <ResultsView
        outputs={{}}
        isDone={false}
        runId="run-1"
        workflowId="wf-1"
        onOpenActivity={onOpenActivity}
      />,
    )
    await user.click(screen.getByRole("button", { name: /Go to Activity/ }))
    expect(onOpenActivity).toHaveBeenCalledTimes(1)
  })

  it("says it is waiting on the screening review and lists partial files", async () => {
    const user = userEvent.setup()
    const onOpenReviewScreening = vi.fn()
    render(
      withQuery(
        <ResultsView
          outputs={{}}
          isDone={false}
          runId="run-1"
          workflowId="wf-1"
          historyOutputs={{ protocol: "runs/wf-1/protocol.md" }}
          awaitingReview
          onOpenReviewScreening={onOpenReviewScreening}
        />,
      ),
    )
    expect(screen.getByText("Waiting on your screening review")).toBeInTheDocument()
    expect(screen.getByText("Files so far")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Review screening/ }))
    expect(onOpenReviewScreening).toHaveBeenCalledTimes(1)
  })
})

describe("ResultsView needs revision", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("opens Quality with the audit findings from the banner", async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/manuscript-audit")) {
          return new Response(
            JSON.stringify({
              run_id: "run-1",
              workflow_id: "wf-1",
              latest_run: { audit_run_id: "a", verdict: "major_revisions", passed: false, contract_violations: [] },
              findings: [
                {
                  finding_id: "f1",
                  severity: "major",
                  category: "prisma_counts",
                  evidence: "Counts disagree",
                  recommendation: "Recount",
                  blocking: true,
                },
              ],
              audit_summary: {
                verdict: "major_revisions",
                status_label: "blocked",
                blocking_count: 1,
                total_findings: 1,
                summary: "",
                gate_failure_reasons: [],
                top_recommendations: [],
              },
            }),
            { status: 200 },
          )
        }
        return new Response("{}", { status: 404 })
      }),
    )
    render(
      withQuery(
        <ResultsView
          outputs={{ artifacts: { protocol: "runs/wf-1/protocol.md" } }}
          isDone
          runId="run-1"
          workflowId="wf-1"
          exportRunId="run-1"
          needsRevision
        />,
      ),
    )
    await user.click(screen.getByRole("button", { name: "View audit findings" }))
    expect(await screen.findByText("Counts disagree")).toBeInTheDocument()
    expect(screen.getByText("Prisma counts")).toBeInTheDocument()
    expect(screen.getByText("Blocking")).toBeInTheDocument()
    expect(document.getElementById("audit-findings")).not.toBeNull()
  })
})
