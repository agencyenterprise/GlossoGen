/**
 * textcraft_shared_workspace frontend plug-in.
 *
 * Renders the scenario's own `read_notifications` result (a `WorkspaceWake`)
 * as a chip, and classifies the triggers its world ends a round with.
 */

import type { RoundTriggerOutcome, ScenarioPlugin } from "../scenario-plugin";
import { parseWorkspaceWake, WorkspaceWakeNotification } from "./workspace-wake-notification";

/** The triggers `world.py` ends a round with (`WorkspaceTrigger`); any other trigger is the platform's. */
type WorkspaceTrigger =
  "all_targets_satisfied" | "budget_exhausted" | "actions_exhausted" | "team_tokens_exhausted";

const WORKSPACE_TRIGGER_OUTCOMES: Record<WorkspaceTrigger, RoundTriggerOutcome> = {
  all_targets_satisfied: "success",
  budget_exhausted: "failure",
  actions_exhausted: "failure",
  team_tokens_exhausted: "failure",
};

function isWorkspaceTrigger(trigger: string): trigger is WorkspaceTrigger {
  return trigger in WORKSPACE_TRIGGER_OUTCOMES;
}

function classifyWorkspaceTrigger(trigger: string): RoundTriggerOutcome | null {
  if (!isWorkspaceTrigger(trigger)) return null;
  return WORKSPACE_TRIGGER_OUTCOMES[trigger];
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
