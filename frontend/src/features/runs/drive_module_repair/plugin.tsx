/**
 * Drive-module-repair frontend plug-in.
 *
 * Surfaces the per-round case-detail header (each unit's faults with the
 * expected component, tool, torque, and calibration) in the round-timeline
 * modal. Uses the standard knobs-preset picker; the replacement-judge verdict
 * per `service_component` call is carried in
 * `scenario_extras.judge_ground_truth_by_call_id` and rendered through the
 * platform's generic judge-metadata display.
 */

import type { ScenarioPlugin } from "../scenario-plugin";
import { DriveModuleRepairRoundDetailPanel } from "./drive-module-repair-round-detail-panel";

export const driveModuleRepairPlugin: ScenarioPlugin = {
  scenarioName: "drive_module_repair",
  primaryChannelId: "bay",
  knobsForm: null,
  RoundDetailPanel: DriveModuleRepairRoundDetailPanel,
  defaultReplaceAgentKnobs: {},
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: {
    sseEventNames: ["drive_module_replacement_judged"],
    judgedToolNames: ["service_component", "replace_component"],
  },
  getTimelineMarkers: () => [],
  classifyRoundTrigger: () => null,
};
