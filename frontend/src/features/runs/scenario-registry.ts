/**
 * Frontend scenario plug-in registry.
 *
 * Each scenario that wants to contribute scenario-specific UI ships a
 * `frontend/src/features/runs/<scenario>/plugin.ts` exporting a
 * `ScenarioPlugin` instance. The registry below imports them eagerly
 * and exposes a single `getScenarioPlugin(name)` lookup; unknown
 * scenario names resolve to `DEFAULT_SCENARIO_PLUGIN` so the platform
 * UI is always safe to call into.
 */

import { containerYardStackingPlugin } from "./container_yard_stacking/plugin";
import { DEFAULT_SCENARIO_PLUGIN } from "./default-plugin";
import { driveModuleRepairPlugin } from "./drive_module_repair/plugin";
import { orbitalAnomalyPlugin } from "./orbital_anomaly/plugin";
import type { ScenarioPlugin } from "./scenario-plugin";
import { spotTheDifferencePlugin } from "./spot_the_difference/plugin";
import { veyruPlugin } from "./veyru/plugin";

const SCENARIO_PLUGINS: Record<string, ScenarioPlugin> = {
  [veyruPlugin.scenarioName]: veyruPlugin,
  [containerYardStackingPlugin.scenarioName]: containerYardStackingPlugin,
  [orbitalAnomalyPlugin.scenarioName]: orbitalAnomalyPlugin,
  [driveModuleRepairPlugin.scenarioName]: driveModuleRepairPlugin,
  [spotTheDifferencePlugin.scenarioName]: spotTheDifferencePlugin,
};

/**
 * Primary channel for scenarios that ship no plug-in.
 *
 * Must match the scenario's `get_primary_channels()` on the backend. The
 * round timeline filters messages on this, so a mismatch renders an empty
 * list under a misleading header rather than failing — which is how
 * spillway_release, warehouse_robot_recovery and
 * hospital_bed_assignment_privacy silently showed nothing while the default
 * assumed every scenario used "link".
 *
 * Scenarios with a plug-in declare `primaryChannelId` there instead.
 */
const PRIMARY_CHANNEL_OVERRIDES: Record<string, string> = {
  spillway_release: "ops",
  warehouse_robot_recovery: "radio",
  hospital_bed_assignment_privacy: "public_ops",
};

/** Return the plug-in registered for ``scenarioName`` or the default no-op plug-in. */
export function getScenarioPlugin(scenarioName: string): ScenarioPlugin {
  const plugin = SCENARIO_PLUGINS[scenarioName];
  if (plugin !== undefined) return plugin;
  const primaryChannelId = PRIMARY_CHANNEL_OVERRIDES[scenarioName];
  if (primaryChannelId !== undefined) {
    return { ...DEFAULT_SCENARIO_PLUGIN, scenarioName, primaryChannelId };
  }
  return DEFAULT_SCENARIO_PLUGIN;
}
