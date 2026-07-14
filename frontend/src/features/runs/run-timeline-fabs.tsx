"use client";

import type { components } from "@/types/api.gen";
import {
  AgentSwapPointFab,
  CrossRunReplaceAgentPointFab,
  ForkPointFab,
  ReplaceAgentPointFab,
} from "./fork-badge";
import { ScenarioMarkerFab } from "./scenario-timeline-marker";
import type { ScenarioTimelineMarker } from "./scenario-plugin";

type ForkSource = components["schemas"]["ForkSource"];
type ReplaceAgentSource = components["schemas"]["ReplaceAgentSource"];
type CrossRunReplaceAgentSource = components["schemas"]["CrossRunReplaceAgentSource"];
type AgentSwapEvent = components["schemas"]["AgentSwapEventDTO"];

/**
 * Floating jump-to buttons stacked at the edge of the run viewer: fork point,
 * scenario markers, replace-agent / cross-run boundaries, and in-run agent
 * swaps. Each button's ``stackIndex`` positions it in the shared vertical
 * stack. Navigation itself is delegated to the parent via ``onScrollToDivider``
 * (scroll to a divider element) and ``onNavigateToForkPoint`` (highlight the
 * fork-point message).
 */
export function RunTimelineFabs({
  forkSource,
  replaceAgentSource,
  crossRunReplaceAgentSource,
  scenarioMarkers,
  swapEvents,
  onScrollToDivider,
  onNavigateToForkPoint,
}: {
  forkSource: ForkSource | null;
  replaceAgentSource: ReplaceAgentSource | null;
  crossRunReplaceAgentSource: CrossRunReplaceAgentSource | null;
  scenarioMarkers: ScenarioTimelineMarker[];
  swapEvents: AgentSwapEvent[];
  onScrollToDivider: (elementId: string) => void;
  onNavigateToForkPoint: (targetMessageId: string) => void;
}) {
  let nextStackIndex = 0;
  const forkStackIndex = forkSource !== null ? nextStackIndex++ : null;
  const scenarioMarkerStackStart = nextStackIndex;
  nextStackIndex += scenarioMarkers.length;
  const replaceAgentStackIndex = replaceAgentSource !== null ? nextStackIndex++ : null;
  const crossRunReplaceStackIndex = crossRunReplaceAgentSource !== null ? nextStackIndex++ : null;

  return (
    <>
      {forkSource && forkStackIndex !== null ? (
        <ForkPointFab
          stackIndex={forkStackIndex}
          onClick={() => onNavigateToForkPoint(forkSource.target_message_id)}
        />
      ) : null}

      {scenarioMarkers.map((marker, i) => (
        <ScenarioMarkerFab
          key={marker.id}
          marker={marker}
          stackIndex={scenarioMarkerStackStart + i}
          onClick={() => onScrollToDivider(marker.id)}
        />
      ))}

      {replaceAgentSource && replaceAgentStackIndex !== null ? (
        <ReplaceAgentPointFab
          stackIndex={replaceAgentStackIndex}
          roundNumber={replaceAgentSource.round_start}
          onClick={() => onScrollToDivider("replace-agent-divider")}
        />
      ) : null}

      {crossRunReplaceAgentSource && crossRunReplaceStackIndex !== null ? (
        <CrossRunReplaceAgentPointFab
          stackIndex={crossRunReplaceStackIndex}
          roundNumber={crossRunReplaceAgentSource.round_start}
          onClick={() => onScrollToDivider("cross-run-replace-agent-divider")}
        />
      ) : null}

      {swapEvents.map(swap => (
        <AgentSwapPointFab
          key={`agent-swap-${swap.round_number}-${swap.agent_id}`}
          stackIndex={nextStackIndex++}
          roundNumber={swap.round_number}
          agentId={swap.agent_id}
          onClick={() =>
            onScrollToDivider(`agent-swap-divider-r${swap.round_number}-${swap.agent_id}`)
          }
        />
      ))}
    </>
  );
}
