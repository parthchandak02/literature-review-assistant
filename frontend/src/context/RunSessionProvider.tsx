import type { ReactNode } from "react"
import { RunSessionContext } from "@/context/runSessionContext"
import { useRunSessionState } from "@/hooks/useRunSessionState"

export function RunSessionProvider({ children }: { children: ReactNode }) {
  const value = useRunSessionState()
  return <RunSessionContext.Provider value={value}>{children}</RunSessionContext.Provider>
}
