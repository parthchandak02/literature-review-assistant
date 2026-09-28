import { describe, expect, it } from "vitest"
import {
  announcementFor,
  countNewEvents,
  newEventsLabel,
  nextFollowState,
  pauseFollow,
  resumeFollow,
} from "./logFollow"

const items = (kinds: string[]) => kinds.map((kind) => ({ kind }))

describe("follow mode", () => {
  it("pauses when the user scrolls up and resumes at the bottom", () => {
    let state = resumeFollow(10)
    state = nextFollowState(state, { atEnd: false, scrolledBackward: false, count: 10 })
    expect(state.following).toBe(true)

    state = nextFollowState(state, { atEnd: false, scrolledBackward: true, count: 10 })
    expect(state).toEqual({ following: false, anchor: 10 })

    state = nextFollowState(state, { atEnd: false, scrolledBackward: false, count: 14 })
    expect(state).toEqual({ following: false, anchor: 10 })

    state = nextFollowState(state, { atEnd: true, scrolledBackward: false, count: 14 })
    expect(state).toEqual({ following: true, anchor: 14 })
  })

  it("returns the same state object when nothing changes", () => {
    const state = resumeFollow(5)
    expect(nextFollowState(state, { atEnd: true, scrolledBackward: false, count: 5 })).toBe(state)
  })
})

describe("new events pill", () => {
  it("counts only event rows appended after the anchor", () => {
    const list = items(["phase-sep", "event", "event", "phase-sep", "event", "event", "event"])
    expect(countNewEvents(list, pauseFollow(3))).toBe(3)
    expect(countNewEvents(list, pauseFollow(1))).toBe(5)
  })

  it("is zero while following or when the list shrank below the anchor", () => {
    const list = items(["event", "event"])
    expect(countNewEvents(list, resumeFollow(0))).toBe(0)
    expect(countNewEvents(list, pauseFollow(5))).toBe(0)
  })

  it("labels singular and plural", () => {
    expect(newEventsLabel(1)).toBe("1 new event")
    expect(newEventsLabel(14)).toBe("14 new events")
  })
})

describe("announcementFor", () => {
  it("announces only phase transitions and errors", () => {
    expect(announcementFor([{ kind: "event" }, { kind: "event" }])).toBeNull()
    expect(announcementFor([{ kind: "phase-sep", label: "Screening" }, { kind: "event" }])).toBe(
      "Now in Screening.",
    )
    expect(announcementFor([{ kind: "event", isError: true, message: "boom" }])).toBe("Error: boom")
    expect(
      announcementFor([
        { kind: "phase-sep", label: "Extraction" },
        { kind: "event", isError: true, message: "a" },
        { kind: "event", isError: true, message: "b" },
      ]),
    ).toBe("Now in Extraction. 2 new errors. Latest: b")
  })
})
