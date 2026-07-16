import { describe, expect, it } from "vitest"
import { historyQueryKey } from "./useHistory"

describe("historyQueryKey", () => {
  it("includes run root so cache keys differ by registry root", () => {
    expect(historyQueryKey()).toEqual(["history", "runs"])
    expect(historyQueryKey("custom-root")).toEqual(["history", "custom-root"])
    expect(historyQueryKey()).not.toEqual(historyQueryKey("custom-root"))
  })
})
