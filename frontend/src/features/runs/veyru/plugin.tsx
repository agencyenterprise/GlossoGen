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

import type { AgentModelOverride } from "../agent-model-overrides";
import type { KnobsFormError, ScenarioPlugin } from "../scenario-plugin";
import { VeyruKnobsForm } from "./veyru-knobs-form";
import { VeyruRoundDetailPanel } from "./veyru-round-detail-panel";
import {
  buildPayload as buildVeyruPayload,
  validateState as validateVeyruState,
  type VeyruKnobsState,
} from "./veyru-knobs-state";

type ModelOption = { model_prefix: string; provider: string };

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
};
