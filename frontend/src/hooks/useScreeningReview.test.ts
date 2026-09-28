// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import type { ScreeningOverride } from "@/lib/api"
import {
  UNDO_LIMIT,
  countPendingScreening,
  initialReviewState,
  moveFocus,
  readOverrides,
  reviewReducer,
  screeningOverridesStorageKey,
  type ReviewAction,
  type ReviewState,
} from "./useScreeningReview"

function run(state: ReviewState, ...actions: ReviewAction[]): ReviewState {
  return actions.reduce(reviewReducer, state)
}

const decide = (key: string, ai: "include" | "exclude" | "uncertain", decision: "include" | "exclude"): ReviewAction => ({
  type: "decide",
  targets: [{ key, ai }],
  decision,
})

describe("reviewReducer decisions", () => {
  it("creates an override only for the action opposite to the AI decision", () => {
    const s0 = initialReviewState()
    const same = run(s0, decide("a", "include", "include"))
    expect(same.overrides.size).toBe(0)
    expect(same.undoStack).toHaveLength(0)
    expect(same.reviewed.has("a")).toBe(true)

    const flipped = run(s0, decide("a", "include", "exclude"))
    expect(flipped.overrides.get("a")).toEqual({ paper_id: "a", decision: "exclude" })
  })

  it("clears an existing override when the AI-matching action is chosen", () => {
    const s = run(initialReviewState(), decide("a", "include", "exclude"), decide("a", "include", "include"))
    expect(s.overrides.has("a")).toBe(false)
    expect(s.undoStack).toHaveLength(2)
  })

  it("lets either action override an uncertain paper and keeps the reason when flipping", () => {
    const s = run(
      initialReviewState(),
      decide("u", "uncertain", "include"),
      { type: "setReason", key: "u", reason: "meets PICO" },
      decide("u", "uncertain", "exclude"),
    )
    expect(s.overrides.get("u")).toEqual({ paper_id: "u", decision: "exclude", reason: "meets PICO" })
  })

  it("applies bulk decisions as one undo step", () => {
    const s = run(initialReviewState(), {
      type: "decide",
      targets: [
        { key: "a", ai: "include" },
        { key: "b", ai: "uncertain" },
        { key: "c", ai: "include" },
      ],
      decision: "exclude",
    })
    expect(Array.from(s.overrides.keys())).toEqual(["a", "b", "c"])
    expect(s.undoStack).toHaveLength(1)
    expect(run(s, { type: "undo" }).overrides.size).toBe(0)
  })

  it("clears selected overrides", () => {
    const s = run(
      initialReviewState(),
      decide("a", "include", "exclude"),
      decide("b", "include", "exclude"),
      { type: "clearOverrides", keys: ["a", "zzz"] },
    )
    expect(Array.from(s.overrides.keys())).toEqual(["b"])
  })
})

describe("reviewReducer undo stack", () => {
  it("undoes multiple levels in order", () => {
    const s = run(
      initialReviewState(),
      decide("a", "include", "exclude"),
      decide("b", "include", "exclude"),
      decide("a", "include", "include"),
    )
    expect(Array.from(s.overrides.keys())).toEqual(["b"])
    const u1 = run(s, { type: "undo" })
    expect(Array.from(u1.overrides.keys()).sort()).toEqual(["a", "b"])
    const u2 = run(u1, { type: "undo" })
    expect(Array.from(u2.overrides.keys())).toEqual(["a"])
    const u3 = run(u2, { type: "undo" })
    expect(u3.overrides.size).toBe(0)
    expect(run(u3, { type: "undo" })).toBe(u3)
  })

  it("does not record reason edits or no-ops, and caps its depth", () => {
    let s = run(initialReviewState(), decide("a", "include", "exclude"), {
      type: "setReason",
      key: "a",
      reason: "x",
    })
    expect(s.undoStack).toHaveLength(1)
    for (let i = 0; i < UNDO_LIMIT + 10; i += 1) {
      s = run(s, decide(`p${i}`, "include", "exclude"))
    }
    expect(s.undoStack).toHaveLength(UNDO_LIMIT)
  })
})

describe("reviewReducer view state", () => {
  it("snapshots overrides for filtering when the filter changes", () => {
    const s = run(initialReviewState(), decide("a", "include", "exclude"), { type: "setFilter", filter: "overridden" })
    expect(s.filterBasis.has("a")).toBe(true)
    const cleared = run(s, { type: "clearOverrides", keys: ["a"] })
    expect(cleared.filterBasis.has("a")).toBe(true)
    expect(cleared.overrides.has("a")).toBe(false)
  })

  it("marks rows reviewed when expanded and toggles selection", () => {
    const s = run(
      initialReviewState(),
      { type: "toggleExpanded", key: "a" },
      { type: "toggleSelected", key: "b" },
      { type: "setSelected", keys: ["c", "d"], selected: true },
      { type: "toggleSelected", key: "b" },
    )
    expect(s.reviewed.has("a")).toBe(true)
    expect(s.focusedKey).toBe("a")
    expect(Array.from(s.selected)).toEqual(["c", "d"])
  })
})

describe("moveFocus", () => {
  const keys = ["a", "b", "c"]
  it("starts at the ends, moves and clamps", () => {
    expect(moveFocus(keys, null, 1)).toBe("a")
    expect(moveFocus(keys, null, -1)).toBe("c")
    expect(moveFocus(keys, "a", 1)).toBe("b")
    expect(moveFocus(keys, "c", 1)).toBe("c")
    expect(moveFocus(keys, "a", -1)).toBe("a")
    expect(moveFocus([], "a", 1)).toBeNull()
  })
})

describe("readOverrides", () => {
  afterEach(() => sessionStorage.clear())

  it("reads persisted overrides including their reasons", () => {
    const stored: ScreeningOverride[] = [
      { paper_id: "a", decision: "exclude", reason: "wrong population" },
      { paper_id: "b", decision: "maybe" as "include" },
    ]
    sessionStorage.setItem(screeningOverridesStorageKey("wf"), JSON.stringify(stored))
    const map = readOverrides(screeningOverridesStorageKey("wf"))
    expect(Array.from(map.values())).toEqual([{ paper_id: "a", decision: "exclude", reason: "wrong population" }])
  })
})

describe("countPendingScreening", () => {
  it("counts include and uncertain final decisions", () => {
    const base = { title: "", authors: "", year: null, source_database: "", doi: null, abstract: null, stage: "fulltext", reason: null, confidence: null }
    expect(countPendingScreening(undefined)).toBeNull()
    expect(
      countPendingScreening({
        run_id: "r",
        total: 3,
        instructions: "",
        papers: [
          { ...base, paper_id: "a", decision: "include" },
          { ...base, paper_id: "b", decision: "uncertain", final_decision: "uncertain" },
          { ...base, paper_id: "c", decision: "exclude", final_decision: "exclude" },
        ],
      }),
    ).toBe(2)
  })
})
