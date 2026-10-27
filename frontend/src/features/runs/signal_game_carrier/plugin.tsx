/**
 * signal_game_carrier frontend plug-in.
 *
 * Surfaces the per-round detail panel in the round-timeline modal: both players'
 * private grids with the square each picked, the round's song drawn with the
 * recording both heard, the noise each player added, the channel noise, and the
 * executors that produced the noise.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { SignalGameCarrierRoundDetailPanel } from "./signal-game-carrier-round-detail-panel";

export const signalGameCarrierPlugin: ScenarioPlugin = {
  scenarioName: "signal_game_carrier",
  RoundDetailPanel: SignalGameCarrierRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
