/**
 * Container-yard-stacking frontend plug-in.
 *
 * Surfaces the per-round case-detail header (active stations, layout,
 * manifest, per-step expected plan) in the round-timeline modal. The
 * inline per-tool-call verdict rendering for ``move_truck`` /
 * ``place_on_stack`` / ``lift_from_stack`` lives on ``DisplayEntry`` and is
 * rendered directly by the platform's ``ToolCallDisplay``.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { YardRoundDetailPanel } from "./yard-round-detail-panel";

export const containerYardStackingPlugin: ScenarioPlugin = {
  scenarioName: "container_yard_stacking",
  knobsForm: null,
  RoundDetailPanel: YardRoundDetailPanel,
  defaultReplaceAgentKnobs: {},
  renderToolMetadata: () => null,
};
