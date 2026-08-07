/**
 * spot_the_difference frontend plug-in.
 *
 * Surfaces the per-round detail panel in the round-timeline modal: the two
 * scenes as mini-grids with the planted differences highlighted, the list of
 * differences, and each team's submission plus its pass/fail reason. Uses the
 * standard preset picker for the knobs form.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { SpotTheDifferenceRoundDetailPanel } from "./spot-the-difference-round-detail-panel";

export const spotTheDifferencePlugin: ScenarioPlugin = {
  scenarioName: "spot_the_difference",
  primaryChannelId: "link",
  RoundDetailPanel: SpotTheDifferenceRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
};
