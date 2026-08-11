/**
 * Container-yard-stacking frontend plug-in.
 *
 * Surfaces the per-round case-detail header (batch assignment of each
 * container's intake slot → target bay, plus row occupancy) in the
 * round-timeline modal and the full knobs form (mode selector + per-mode
 * fields + shared settings) for the "Create simulation" page.
 */

import type { components } from "@/types/api.gen";
import type { ScenarioPlugin } from "../scenario-plugin";
import { formatExpectedMove, formatMoveArgs, moveVerdictAccepted } from "./move-verdict";
import { YardMoveMetadataBlock } from "./yard-move-metadata-block";
import { YardRoundDetailPanel } from "./yard-round-detail-panel";

type ContainerYardRunExtras = components["schemas"]["ContainerYardRunExtras"];

function isYardExtras(extras: unknown): extras is ContainerYardRunExtras {
  if (typeof extras !== "object" || extras === null) return false;
  const tagged = extras as { scenario_name?: string };
  return tagged.scenario_name === "container_yard_stacking";
}

export const containerYardStackingPlugin: ScenarioPlugin = {
  scenarioName: "container_yard_stacking",
  RoundDetailPanel: YardRoundDetailPanel,
  renderToolMetadata: ({ callId, extras }) => {
    if (!isYardExtras(extras)) return null;
    const metadata = extras.move_metadata_by_call_id[callId];
    if (metadata === undefined) return null;
    return <YardMoveMetadataBlock metadata={metadata} />;
  },
  summarizeToolVerdict: ({ callId, toolArguments, extras }) => {
    if (!isYardExtras(extras)) return null;
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
  classifyRoundTrigger: () => null,
};
