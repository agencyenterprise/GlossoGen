/**
 * signal_game_server frontend plug-in.
 *
 * Surfaces the plaintext judge's reading of each round in the round-timeline modal:
 * the texts it read and its decision on each, the names it flagged from the tree, and
 * its tool calls.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { SignalGameServerRoundDetailPanel } from "./signal-game-server-round-detail-panel";

export const signalGameServerPlugin: ScenarioPlugin = {
  scenarioName: "signal_game_server",
  RoundDetailPanel: SignalGameServerRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
