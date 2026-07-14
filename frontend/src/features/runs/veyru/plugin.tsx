/**
 * Veyru frontend plug-in.
 *
 * Bundles the Veyru-specific knobs form, the round-detail header panel,
 * the per-tool-call judge-verdict renderer, and the default knobs
 * payload used by the cross-run replace-agent modal. The platform UI
 * looks this up via `getScenarioPlugin("veyru")` and routes
 * Veyru-conditional rendering through it instead of hardcoding
 * `scenarioName === "veyru"` checks.
 */

import { ArrowLeftRight, UserCog, UserPlus } from "lucide-react";
import type { components } from "@/types/api.gen";
import type { AgentModelOverride } from "../agent-model-overrides";
import type {
  KnobsFormError,
  RoundTriggerOutcome,
  ScenarioPlugin,
  ScenarioTimelineMarker,
} from "../scenario-plugin";
import { VeyruKnobsForm } from "./veyru-knobs-form";
import { VeyruRoundDetailPanel } from "./veyru-round-detail-panel";
import {
  buildPayload as buildVeyruPayload,
  validateState as validateVeyruState,
  type VeyruKnobsState,
} from "./veyru-knobs-state";

type ModelOption = { model_prefix: string; provider: string };
type VeyruRunExtras = components["schemas"]["VeyruRunExtras"];

/** Narrow the platform's opaque `scenario_extras` payload to the veyru variant. */
function asVeyruExtras(extras: unknown): VeyruRunExtras | null {
  const candidate = extras as VeyruRunExtras | null;
  if (candidate !== null && candidate.scenario_name === "veyru") {
    return candidate;
  }
  return null;
}

/** Build the veyru observer-swap / intern-join / intern-takeover timeline markers. */
function buildVeyruMarkers(extras: unknown): ScenarioTimelineMarker[] {
  const veyru = asVeyruExtras(extras);
  if (veyru === null) {
    return [];
  }
  const markers: ScenarioTimelineMarker[] = [];
  const swap = veyru.swap_point;
  if (swap !== null) {
    const names = swap.swapped_observer_display_names;
    let swapTitle: ScenarioTimelineMarker["dividerTitle"];
    if (names.length === 2) {
      swapTitle = (
        <>
          {names[0]} <span aria-hidden="true">⇄</span> {names[1]} — swapped teams
        </>
      );
    } else {
      swapTitle = "Observers swapped between teams";
    }
    markers.push({
      id: "swap-divider",
      roundNumber: swap.round_number,
      tone: "amber",
      icon: ArrowLeftRight,
      fabLabel: "swap",
      dividerTitle: swapTitle,
      dividerSubtitle: `Channel history was wiped. Round ${swap.round_number} begins with the new pairings.`,
    });
  }
  const internJoin = veyru.intern_join;
  if (internJoin !== null) {
    markers.push({
      id: "intern-join-divider",
      roundNumber: internJoin.round_number,
      tone: "emerald",
      icon: UserPlus,
      fabLabel: "intern join",
      dividerTitle: "Intern Observer joined the comm link",
      dividerSubtitle: `Silent observation begins at round ${internJoin.round_number}. The intern cannot see messages from earlier rounds.`,
    });
  }
  const internTakeover = veyru.intern_takeover;
  if (internTakeover !== null) {
    markers.push({
      id: "intern-takeover-divider",
      roundNumber: internTakeover.round_number,
      tone: "violet",
      icon: UserCog,
      fabLabel: "intern takeover",
      dividerTitle: "Intern Observer took over as Field Observer",
      dividerSubtitle: `The previous Field Observer left the comm link. Round ${internTakeover.round_number} begins with the new pairing.`,
    });
  }
  return markers;
}

/** Tone the veyru round-outcome triggers for the round-timeline badge. */
function classifyVeyruTrigger(trigger: string): RoundTriggerOutcome | null {
  if (trigger === "veyru_stabilized") {
    return "success";
  }
  if (trigger === "veyru_collapsed") {
    return "failure";
  }
  return null;
}

function VeyruKnobsFormAdapter({
  state,
  models,
  errors,
  onChange,
}: {
  state: unknown;
  models: ModelOption[];
  errors: KnobsFormError[];
  onChange: (next: unknown) => void;
}) {
  return (
    <VeyruKnobsForm
      state={state as VeyruKnobsState | null}
      models={models}
      errors={errors as { field: keyof VeyruKnobsState; message: string }[]}
      onChange={next => onChange(next)}
    />
  );
}

export const veyruPlugin: ScenarioPlugin = {
  scenarioName: "veyru",
  primaryChannelId: "link",
  knobsForm: {
    Component: VeyruKnobsFormAdapter,
    validate: state => validateVeyruState(state as VeyruKnobsState),
    buildPayload: ({ state, modelOverrides }) =>
      buildVeyruPayload({
        state: state as VeyruKnobsState,
        modelOverrides: modelOverrides as Record<string, AgentModelOverride>,
      }),
  },
  RoundDetailPanel: VeyruRoundDetailPanel,
  defaultReplaceAgentKnobs: { postmortem_disabled_at_start: true },
  renderToolMetadata: () => null,
  summarizeToolVerdict: () => null,
  liveJudge: {
    sseEventNames: ["veyru_stabilization_judged"],
    judgedToolNames: ["stabilize_veyru"],
  },
  getTimelineMarkers: ({ extras }) => buildVeyruMarkers(extras),
  classifyRoundTrigger: classifyVeyruTrigger,
};
