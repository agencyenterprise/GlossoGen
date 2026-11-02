/**
 * signal_game frontend plug-in.
 *
 * Surfaces each round's two grids in the round-timeline modal: the colours or coloured
 * shapes on each, which items both grids share, where each player started and
 * finished, and both players' actions in order with the private reasoning on each.
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
