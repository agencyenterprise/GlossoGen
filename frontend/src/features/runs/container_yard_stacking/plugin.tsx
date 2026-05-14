/**
 * Container-yard-stacking frontend plug-in.
 *
 * Surfaces the per-round case-detail header in the round-timeline modal
 * and the full knobs form (mode selector + per-mode fields + shared
 * settings) for the "Create simulation" page. The inline per-tool-call
 * verdict rendering for ``move_truck`` / ``place_on_stack`` /
 * ``lift_from_stack`` lives on ``DisplayEntry`` and is rendered directly
 * by the platform's ``ToolCallDisplay``.
 */

import type { AgentModelOverride } from "../agent-model-overrides";
import type { KnobsFormError, ScenarioPlugin } from "../scenario-plugin";
import { ContainerYardKnobsForm } from "./container-yard-knobs-form";
import {
  buildPayload as buildContainerYardPayload,
  knobsToState,
  validateState as validateContainerYardState,
  type ContainerYardKnobsState,
} from "./container-yard-knobs-state";
import { YardRoundDetailPanel } from "./yard-round-detail-panel";

function ContainerYardKnobsFormAdapter({
  state,
  errors,
  onChange,
}: {
  state: unknown;
  models: { model_prefix: string; provider: string }[];
  errors: KnobsFormError[];
  onChange: (next: unknown) => void;
}) {
  const typedState = state as ContainerYardKnobsState | null;
  const typedErrors = errors as { field: keyof ContainerYardKnobsState; message: string }[];
  if (typedState === null) {
    const seeded = knobsToState({});
    return (
      <ContainerYardKnobsForm
        state={seeded}
        errors={typedErrors}
        onChange={next => onChange(next)}
      />
    );
  }
  return (
    <ContainerYardKnobsForm
      state={typedState}
      errors={typedErrors}
      onChange={next => onChange(next)}
    />
  );
}

export const containerYardStackingPlugin: ScenarioPlugin = {
  scenarioName: "container_yard_stacking",
  knobsForm: {
    Component: ContainerYardKnobsFormAdapter,
    validate: state => validateContainerYardState(state as ContainerYardKnobsState),
    buildPayload: ({ state, modelOverrides }) =>
      buildContainerYardPayload({
        state: state as ContainerYardKnobsState,
        modelOverrides: modelOverrides as Record<string, AgentModelOverride>,
      }),
  },
  RoundDetailPanel: YardRoundDetailPanel,
  defaultReplaceAgentKnobs: { postmortem_disabled_at_start: true },
  renderToolMetadata: () => null,
};
