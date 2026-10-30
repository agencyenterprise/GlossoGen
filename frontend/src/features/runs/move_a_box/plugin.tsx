/**
 * move_a_box frontend plug-in.
 *
 * Surfaces the per-round floor plans in the round-timeline modal: each
 * operator's pallets and bays, the path its crate took with the method that
 * carried each step, and both crates' temperature readings on one scale.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { MoveABoxRoundDetailPanel } from "./move-a-box-round-detail-panel";

export const moveABoxPlugin: ScenarioPlugin = {
  scenarioName: "move_a_box",
  RoundDetailPanel: MoveABoxRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
