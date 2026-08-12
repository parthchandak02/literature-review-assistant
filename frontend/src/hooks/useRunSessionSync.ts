import type { Dispatch, SetStateAction } from "react"
import type { NavigateFunction } from "react-router-dom"
import type { useLiveRunStream } from "@/hooks/useLiveRunStream"
import { useRunSessionArtifactsSync } from "@/hooks/runSession/useRunSessionArtifactsSync"
import { useRunSessionLiveEffects } from "@/hooks/runSession/useRunSessionLiveEffects"
import { useRunSessionUrlSync } from "@/hooks/runSession/useRunSessionUrlSync"
import type { RunTab, SelectedRun } from "@/views/RunView"

type LiveStream = ReturnType<typeof useLiveRunStream>

export interface RunSessionSyncArgs {
  navigate: NavigateFunction
  pathname: string
  selectedRun: SelectedRun | null
  setSelectedRun: Dispatch<SetStateAction<SelectedRun | null>>
  activeRunTab: RunTab
  setActiveRunTab: Dispatch<SetStateAction<RunTab>>
  setHistoryOutputs: Dispatch<SetStateAction<Record<string, string>>>
  isViewingLiveRun: boolean
  live: LiveStream
}

export function useRunSessionSync(args: RunSessionSyncArgs) {
  useRunSessionUrlSync(args)
  useRunSessionLiveEffects(args)
  useRunSessionArtifactsSync(args)
}
