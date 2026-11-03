/**
 * Container-yard-stacking frontend plug-in.
 *
 * Surfaces the per-round case-detail header (batch assignment of each
 * container's intake slot → target bay, plus row occupancy) in the
 * round-timeline modal and the full knobs form (mode selector + per-mode
 * fields + shared settings) for the "Create simulation" page.
 */

import {
  isScenarioExtras,
  type RoundTriggerOutcome,
  type ScenarioPlugin,
} from "../scenario-plugin";
import { formatExpectedMove, formatMoveArgs, moveVerdictAccepted } from "./move-verdict";
import { YardMoveMetadataBlock } from "./yard-move-metadata-block";
import { YardRoundDetailPanel } from "./yard-round-detail-panel";

/** The triggers `scenario.py` ends a round with; any other trigger is the platform's. */
const YARD_TRIGGER_OUTCOMES: Record<string, RoundTriggerOutcome> = {
  round_completed: "success",
  round_failed: "failure",
};

function classifyYardTrigger(trigger: string): RoundTriggerOutcome | null {
  return YARD_TRIGGER_OUTCOMES[trigger] ?? null;
}

export const containerYardStackingPlugin: ScenarioPlugin = {
  scenarioName: "container_yard_stacking",
  RoundDetailPanel: YardRoundDetailPanel,
  renderToolMetadata: ({ callId, extras }) => {
    if (!isScenarioExtras(extras, "container_yard_stacking")) return null;
    const metadata = extras.move_metadata_by_call_id[callId];
    if (metadata === undefined) return null;
    return <YardMoveMetadataBlock metadata={metadata} />;
  },
  summarizeToolVerdict: ({ callId, toolArguments, extras }) => {
    if (!isScenarioExtras(extras, "container_yard_stacking")) return null;
    const metadata = extras.move_metadata_by_call_id[callId];
    if (metadata === undefined) return null;
    return {
      accepted: moveVerdictAccepted(metadata),
      expected: formatExpectedMove(metadata),
      explanation: metadata.explanation,
      toolLabel: "move_container",
      actionText: formatMoveArgs(toolArguments),
    };
  },
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: classifyYardTrigger,
  renderNotification: () => null,
};
