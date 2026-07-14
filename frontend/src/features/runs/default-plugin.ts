/**
 * Default no-op scenario plug-in used by every scenario that does not
 * register a custom one. Mirrors the contract in `scenario-plugin.ts`
 * but every slot returns null / an empty record so the platform UI
 * falls back to its generic rendering.
 */

import type { ScenarioPlugin } from "./scenario-plugin";

export const DEFAULT_SCENARIO_PLUGIN: ScenarioPlugin = {
  scenarioName: "__default__",
  primaryChannelId: "link",
  knobsForm: null,
  RoundDetailPanel: null,
  defaultReplaceAgentKnobs: {},
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
};
