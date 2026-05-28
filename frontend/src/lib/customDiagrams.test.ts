import { describe, expect, it } from "vitest"
import {
  collectCustomDiagramItems,
  customDiagramPipelineTouched,
  findArtifactPath,
  titleForCustomDiagram,
} from "./customDiagrams"

describe("customDiagrams", () => {
  it("collects custom diagram paths from artifacts map", () => {
    const outputs = {
      artifacts: {
        custom_diagram_01: "/runs/wf/fig_custom_01.png",
        custom_diagram_02: "/runs/wf/fig_custom_02.png",
        prisma_diagram: "/runs/wf/fig_prisma_flow.png",
      },
    }
    const items = collectCustomDiagramItems(outputs)
    expect(items).toHaveLength(2)
    expect(items[0]?.index).toBe(1)
    expect(items[0]?.path).toContain("fig_custom_01.png")
  })

  it("detects pipeline artifacts even when PNGs are missing", () => {
    const outputs = {
      artifacts: {
        diagram_generation_report: "/runs/wf/data_diagram_generation_report.json",
      },
    }
    expect(customDiagramPipelineTouched(outputs)).toBe(true)
    expect(collectCustomDiagramItems(outputs)).toHaveLength(0)
  })

  it("resolves artifact keys and titles", () => {
    const outputs = { artifacts: { diagram_brief_pack: "/runs/wf/data_diagram_brief_pack.json" } }
    expect(findArtifactPath(outputs, "diagram_brief_pack")).toContain("data_diagram_brief_pack.json")
    expect(titleForCustomDiagram(1, [{ title: "Drone delivery times" }])).toBe("Drone delivery times")
    expect(titleForCustomDiagram(2, null)).toMatch(/methodological/i)
  })
})
