/**
 * signal_game frontend plug-in.
 *
 * Surfaces the plaintext judge's reading of each ``file_system`` round in the
 * round-timeline modal: the texts it read and its decision on each, the names it
 * flagged from the tree, and its tool calls. The ``grid`` medium calls no judge and
 * shows no panel.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { SignalGameRoundDetailPanel } from "./signal-game-round-detail-panel";

export const signalGamePlugin: ScenarioPlugin = {
  scenarioName: "signal_game",
  RoundDetailPanel: SignalGameRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
