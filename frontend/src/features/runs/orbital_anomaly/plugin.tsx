/**
 * Orbital-anomaly frontend plug-in.
 *
 * Surfaces the per-round anomaly case-detail header (cockpit alarm, panel
 * observation, telemetry readout, and expected corrective action per stage)
 * in the round-timeline modal. Uses the standard knobs-preset picker; the
 * actuation-judge verdict per `actuate_panel` call is carried in
 * `scenario_extras.actuation_metadata_by_call_id` for the platform tool-call
 * display.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { OrbitalAnomalyRoundDetailPanel } from "./orbital-anomaly-round-detail-panel";

export const orbitalAnomalyPlugin: ScenarioPlugin = {
  scenarioName: "orbital_anomaly",
  primaryChannelId: "link",
  knobsForm: null,
  RoundDetailPanel: OrbitalAnomalyRoundDetailPanel,
  defaultReplaceAgentKnobs: {},
  renderToolMetadata: () => null,
};
