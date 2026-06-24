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
import { orbitalAnomalyPlugin } from "./orbital_anomaly/plugin";
import type { ScenarioPlugin } from "./scenario-plugin";
import { veyruPlugin } from "./veyru/plugin";

const SCENARIO_PLUGINS: Record<string, ScenarioPlugin> = {
  [veyruPlugin.scenarioName]: veyruPlugin,
  [containerYardStackingPlugin.scenarioName]: containerYardStackingPlugin,
  [orbitalAnomalyPlugin.scenarioName]: orbitalAnomalyPlugin,
};

/** Return the plug-in registered for ``scenarioName`` or the default no-op plug-in. */
export function getScenarioPlugin(scenarioName: string): ScenarioPlugin {
  return SCENARIO_PLUGINS[scenarioName] ?? DEFAULT_SCENARIO_PLUGIN;
}
