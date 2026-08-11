import { useContext } from "react"
import {
  RunSessionActionsContext,
  RunSessionStateContext,
} from "@/context/runSessionContext"
import type {
  RunSessionActionsContextValue,
  RunSessionContextValue,
  RunSessionStateContextValue,
} from "@/context/runSessionTypes"

export function useRunSessionState(): RunSessionStateContextValue {
  const ctx = useContext(RunSessionStateContext)
  if (!ctx) {
    throw new Error("useRunSessionState must be used within RunSessionProvider")
  }
  return ctx
}

export function useRunSessionActions(): RunSessionActionsContextValue {
  const ctx = useContext(RunSessionActionsContext)
  if (!ctx) {
    throw new Error("useRunSessionActions must be used within RunSessionProvider")
  }
  return ctx
}

/** @deprecated Prefer useRunSessionState() and useRunSessionActions() for selective subscriptions. */
export function useRunSession(): RunSessionContextValue {
  const state = useRunSessionState()
  const actions = useRunSessionActions()
  return { ...state, ...actions }
}
