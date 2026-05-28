import { useContext } from "react"
import { RunSessionContext } from "@/context/runSessionContext"
import type { RunSessionContextValue } from "@/context/runSessionTypes"

export function useRunSession(): RunSessionContextValue {
  const ctx = useContext(RunSessionContext)
  if (!ctx) {
    throw new Error("useRunSession must be used within RunSessionProvider")
  }
  return ctx
}
