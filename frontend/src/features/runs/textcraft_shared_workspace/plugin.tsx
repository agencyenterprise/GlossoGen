/**
 * textcraft_shared_workspace frontend plug-in.
 *
 * Renders the scenario's own `read_notifications` result (a `WorkspaceWake`)
 * as a chip, and classifies the triggers its world ends a round with.
 */

import type { RoundTriggerOutcome, ScenarioPlugin } from "../scenario-plugin";
import { parseWorkspaceWake, WorkspaceWakeNotification } from "./workspace-wake-notification";

/** The triggers `world.py` ends a round with; any other trigger is the platform's. */
function classifyWorkspaceTrigger(trigger: string): RoundTriggerOutcome | null {
  if (trigger === "all_targets_satisfied") return "success";
  if (trigger === "budget_exhausted" || trigger === "actions_exhausted") return "failure";
  return null;
}

export const textcraftSharedWorkspacePlugin: ScenarioPlugin = {
  scenarioName: "textcraft_shared_workspace",
  RoundDetailPanel: null,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: classifyWorkspaceTrigger,
  renderNotification: ({ payload }) => {
    const wake = parseWorkspaceWake(payload);
    if (wake === null) return null;
    return <WorkspaceWakeNotification wake={wake} />;
  },
};
