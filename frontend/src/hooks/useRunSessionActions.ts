import type { RunSessionActions } from "@/context/runSessionTypes"
import type { RunSessionActionsArgs } from "@/hooks/runSession/runSessionActionDeps"
import { useRunGateActions } from "@/hooks/runSession/useRunGateActions"
import { useRunLifecycleActions } from "@/hooks/runSession/useRunLifecycleActions"
import { useRunLiveConnect } from "@/hooks/runSession/useRunLiveConnect"
import { useRunNavigationActions } from "@/hooks/runSession/useRunNavigationActions"
import { useRunRegistryActions } from "@/hooks/runSession/useRunRegistryActions"

export type { RunSessionActionsArgs } from "@/hooks/runSession/runSessionActionDeps"

export function useRunSessionActions(args: RunSessionActionsArgs): RunSessionActions {
  const liveConnect = useRunLiveConnect(args)
  const navigation = useRunNavigationActions(args)
  const registry = useRunRegistryActions(args)
  const lifecycle = useRunLifecycleActions(args, liveConnect)
  const gate = useRunGateActions({
    selectedRun: args.selectedRun,
    handleResumeRun: liveConnect.handleResumeRun,
  })

  return {
    ...lifecycle,
    ...navigation,
    ...registry,
    ...gate,
  }
}
