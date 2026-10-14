/**
 * dead_drop frontend plug-in.
 *
 * Shows the server's files as each round ended at the top of the round-timeline
 * modal, and beneath each `run_command` call the files it changed or read.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { isDeadDropExtras } from "./dead-drop-extras";
import { DeadDropFilesystemPanel } from "./dead-drop-filesystem-panel";
import { DeadDropFsEffectsBlock } from "./dead-drop-fs-effects-block";

export const deadDropPlugin: ScenarioPlugin = {
  scenarioName: "dead_drop",
  RoundDetailPanel: DeadDropFilesystemPanel,
  renderToolMetadata: ({ callId, extras }) => {
    if (!isDeadDropExtras(extras)) return null;
    const effects = extras.effects_by_call_id[callId];
    if (effects === undefined || effects.length === 0) return null;
    return <DeadDropFsEffectsBlock effects={effects} />;
  },
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
