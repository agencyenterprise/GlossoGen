/**
 * carrier_song frontend plug-in.
 *
 * Surfaces the per-round detail panel in the round-timeline modal: the code sent
 * beside the decoding, the round's song drawn with the recording the receiver
 * heard, the noise the sender added and the channel noise, and the executor that
 * produced the noise.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { CarrierSongRoundDetailPanel } from "./carrier-song-round-detail-panel";

export const carrierSongPlugin: ScenarioPlugin = {
  scenarioName: "carrier_song",
  RoundDetailPanel: CarrierSongRoundDetailPanel,
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: null,
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
  renderNotification: () => null,
};
