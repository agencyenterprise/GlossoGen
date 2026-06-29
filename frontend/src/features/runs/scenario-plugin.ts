/**
 * Scenario plug-in surface for the frontend.
 *
 * Each scenario optionally ships a `ScenarioPlugin` at
 * `frontend/src/features/runs/<scenario>/plugin.ts` and registers it in
 * `scenario-registry.ts`. The platform UI (new-simulation form, round
 * timeline modal, cross-run replace-agent modal, run-detail page) looks
 * up the plug-in by `scenario_name` and routes scenario-specific
 * concerns through it. Scenarios without a registered plug-in get the
 * default no-op surface.
 *
 * Form state is typed as `unknown` at the plug-in boundary so the
 * registry can store every plug-in under a single type without variance
 * conflicts. Each plug-in narrows the state internally with a single
 * cast and exposes its concrete state type to its own form Component.
 */

import type { ComponentType, ReactNode } from "react";
import type { AgentModelOverride } from "./agent-model-overrides";

type KnobsMap = Record<string, unknown>;
type ModelOption = { model_prefix: string; provider: string };

/** Validation error attached to a scenario-specific knobs form field. */
export interface KnobsFormError {
  field: string;
  message: string;
}

/**
 * Adapter wrapping a scenario's bespoke knobs form.
 *
 * The form is expected to self-bootstrap (e.g. load defaults from a
 * preset endpoint) on mount when `state` is `null`.
 */
export interface ScenarioKnobsForm {
  /** Component rendered in place of the standard knobs-preset picker. */
  Component: ComponentType<{
    state: unknown;
    models: ModelOption[];
    errors: KnobsFormError[];
    onChange: (next: unknown) => void;
  }>;
  /** Return field-scoped validation errors. Empty array means valid. */
  validate: (state: unknown) => KnobsFormError[];
  /** Convert form state into the wire-format knobs payload posted to the backend. */
  buildPayload: (args: {
    state: unknown;
    modelOverrides: Record<string, AgentModelOverride>;
  }) => KnobsMap;
}

/** Props for the per-scenario round-detail panel mounted inside the round timeline modal.
 *
 * ``extras`` is the run's ``scenario_extras`` payload typed as ``unknown``
 * so the registry can hold every plug-in under a single type without
 * variance conflicts. Each plug-in narrows it internally with a single
 * cast to its own discriminated-union variant.
 */
export interface RoundDetailPanelProps {
  roundNumber: number;
  extras: unknown;
}

/**
 * Scenario plug-in surface. All fields are nullable — the default
 * plug-in returns null/no-op for every slot.
 */
export interface ScenarioPlugin {
  scenarioName: string;
  /**
   * The primary (budgeted) channel whose messages appear in the
   * round-timeline modal. Defaults to ``"link"`` for scenarios without a
   * registered plug-in.
   */
  primaryChannelId: string;
  /** Bespoke knobs form (null = use the standard preset picker). */
  knobsForm: ScenarioKnobsForm | null;
  /** Header panel rendered above the timeline in the round-detail modal. */
  RoundDetailPanel: ComponentType<RoundDetailPanelProps> | null;
  /**
   * Knobs payload defaulted into the cross-run-replace-agent modal for
   * this scenario. Empty record means no default.
   */
  defaultReplaceAgentKnobs: KnobsMap;
  /**
   * Render scenario-specific supplementary content for a tool-use entry
   * (e.g. judge verdict for veyru's stabilize_veyru, truck/crane verdicts
   * for container_yard_stacking). Returns null when the plug-in has
   * nothing to add for this tool. ``extras`` is the run's
   * ``scenario_extras`` payload typed as ``unknown`` — each plug-in
   * narrows it internally to its own variant.
   */
  renderToolMetadata: (args: { toolName: string; callId: string; extras: unknown }) => ReactNode;
}
