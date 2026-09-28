import { beforeEach, describe, expect, it, vi } from "vitest"
import { APIResponseError } from "@/lib/api"
import {
  INITIAL_PACKAGE_STATE,
  ensureSubmissionPackage,
  forceForAction,
  packageReducer,
  primaryPackageAction,
  rebuildNeedsConfirm,
  resetPackageStore,
  runPackageBuild,
} from "./submissionPackage"

const triggerExport = vi.fn()

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>()
  return { ...actual, triggerExport: (...args: unknown[]) => triggerExport(...args) }
})

const conflict = () => new APIResponseError("incomplete", 409, {})

describe("packageReducer", () => {
  it("syncs from outputs only while unbuilt", () => {
    expect(packageReducer(INITIAL_PACKAGE_STATE, { type: "SYNC", complete: true, partial: false }).status).toBe("ready")
    expect(packageReducer(INITIAL_PACKAGE_STATE, { type: "SYNC", complete: false, partial: true }).status).toBe("incomplete")
    expect(packageReducer(INITIAL_PACKAGE_STATE, { type: "SYNC", complete: false, partial: false })).toBe(INITIAL_PACKAGE_STATE)
    const building = packageReducer(INITIAL_PACKAGE_STATE, { type: "BUILD", force: false })
    expect(packageReducer(building, { type: "SYNC", complete: true, partial: false })).toBe(building)
  })

  it("walks Build → Rebuild → Download", () => {
    let s = INITIAL_PACKAGE_STATE
    expect(primaryPackageAction(s.status)).toBe("build")
    s = packageReducer(s, { type: "BUILD", force: false })
    expect(primaryPackageAction(s.status)).toBeNull()
    s = packageReducer(s, { type: "INCOMPLETE" })
    expect(primaryPackageAction(s.status)).toBe("rebuild")
    expect(rebuildNeedsConfirm(s.status)).toBe(false)
    s = packageReducer(s, { type: "BUILD", force: true })
    s = packageReducer(s, { type: "BUILT", files: ["/r/submission/manuscript.tex"] })
    expect(primaryPackageAction(s.status)).toBe("download")
    expect(rebuildNeedsConfirm(s.status)).toBe(true)
    expect(s.files).toEqual(["/r/submission/manuscript.tex"])
  })

  it("retries with the force flag of the failed attempt", () => {
    let s = packageReducer(INITIAL_PACKAGE_STATE, { type: "BUILD", force: true })
    s = packageReducer(s, { type: "FAILED", error: "boom" })
    expect(s.status).toBe("error")
    expect(primaryPackageAction(s.status)).toBe("retry")
    expect(forceForAction(s, "retry")).toBe(true)
    expect(forceForAction(s, "build")).toBe(false)
    expect(forceForAction(s, "rebuild")).toBe(true)
  })
})

describe("package store", () => {
  beforeEach(() => {
    resetPackageStore()
    triggerExport.mockReset()
  })

  it("download path force-rebuilds after a 409", async () => {
    triggerExport.mockRejectedValueOnce(conflict()).mockResolvedValueOnce({ files: ["a"] })
    const s = await ensureSubmissionPackage("run-1")
    expect(triggerExport.mock.calls).toEqual([["run-1", false], ["run-1", true]])
    expect(s.status).toBe("ready")
  })

  it("download path does not rebuild a ready package", async () => {
    triggerExport.mockResolvedValueOnce({ files: ["a"] })
    await runPackageBuild("run-2", false)
    await ensureSubmissionPackage("run-2")
    expect(triggerExport).toHaveBeenCalledTimes(1)
  })

  it("explicit Build stops at incomplete on 409", async () => {
    triggerExport.mockRejectedValueOnce(conflict())
    const s = await runPackageBuild("run-3", false)
    expect(s.status).toBe("incomplete")
    expect(triggerExport).toHaveBeenCalledTimes(1)
  })

  it("reports failures", async () => {
    triggerExport.mockRejectedValueOnce(new Error("Export failed: disk full"))
    const s = await ensureSubmissionPackage("run-4")
    expect(s.status).toBe("error")
    expect(s.error).toBe("disk full")
  })
})
