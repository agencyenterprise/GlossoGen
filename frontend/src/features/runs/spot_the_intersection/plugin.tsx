/**
 * spot_the_intersection frontend plug-in.
 *
 * Surfaces the per-round detail panel in the round-timeline modal: every seat's
 * board as a mini-grid with the answer and the near-misses marked, and each
 * team's submissions plus its pass/fail reason. Uses the standard preset picker
 * for the knobs form.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { SpotTheIntersectionRoundDetailPanel } from "./spot-the-intersection-round-detail-panel";

export const spotTheIntersectionPlugin: ScenarioPlugin = {
  scenarioName: "spot_the_intersection",
  RoundDetailPanel: SpotTheIntersectionRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  toolCaption: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
