import { createContext } from "react"
import type {
  RunSessionActionsContextValue,
  RunSessionStateContextValue,
} from "@/context/runSessionTypes"

export const RunSessionStateContext = createContext<RunSessionStateContextValue | null>(null)
export const RunSessionActionsContext = createContext<RunSessionActionsContextValue | null>(null)
