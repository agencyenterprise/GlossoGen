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

/** Color palette for a scenario timeline marker's FAB and divider. */
export type ScenarioMarkerTone = "amber" | "emerald" | "violet";

/** Outcome a scenario assigns to one of its `RoundEnded.trigger` values. */
export type RoundTriggerOutcome = "success" | "failure";

/**
 * A round-anchored, scenario-specific event on the run timeline (e.g. veyru's
 * observer swap or intern takeover). The platform renders each marker twice:
 * as a floating jump-to button on the run-detail page and as an inline divider
 * in the chat pane at `roundNumber`. `id` is the shared DOM id linking the two.
 */
export interface ScenarioTimelineMarker {
  id: string;
  roundNumber: number;
  tone: ScenarioMarkerTone;
  icon: ComponentType<{ className?: string }>;
  /** Rendered as "Go to {fabLabel} (round N)" on the floating button. */
  fabLabel: string;
  /** Bold heading on the inline divider. */
  dividerTitle: ReactNode;
  /** Secondary line on the inline divider. */
  dividerSubtitle: ReactNode;
}

/** Validation error attached to a scenario-specific knobs form field. */
export interface KnobsFormError {
  field: string;
  message: string;
}

/**
 * Compact verdict for one tool call, rendered as a row in the round-timeline
 * modal. `accepted` is true/false, or null for a retryable soft-reject.
 * `toolLabel` is the display name for the row and `actionText` the one-line
 * action summary.
 */
export interface ToolVerdictSummary {
  accepted: boolean | null;
  expected: string;
  explanation: string;
  toolLabel: string;
  actionText: string;
}

/**
 * Live-stream wiring for a scenario whose executor emits an LLM-judge verdict.
 *
 * `sseEventNames` are the `*_judged` SSE event names the run stream emits for
 * this scenario; `judgedToolNames` are the tool names whose results carry a
 * verdict, used to attach each queued verdict to its tool call by `call_id`.
 * A scenario with no judged action leaves this `null`.
 */
export interface LiveJudgeConfig {
  sseEventNames: string[];
  judgedToolNames: string[];
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
   * Render a scenario's bespoke supplementary block for a tool-use entry
   * (e.g. the container-yard move verdict). LLM-judged scenarios surface
   * their verdict through the uniform judge metadata instead and return null
   * here. ``extras`` is the run's ``scenario_extras`` payload typed as
   * ``unknown`` — each plug-in narrows it internally to its own variant.
   */
  renderToolMetadata: (args: { toolName: string; callId: string; extras: unknown }) => ReactNode;
  /**
   * Compact tool-call verdict for the round-timeline summary row, or null when
   * the plug-in has no bespoke verdict for this tool. LLM-judged scenarios
   * surface their verdict through the uniform judge metadata instead and
   * return null here. `extras` is `unknown`, narrowed internally.
   */
  summarizeToolVerdict: (args: {
    toolName: string;
    callId: string;
    toolArguments: Record<string, unknown>;
    extras: unknown;
  }) => ToolVerdictSummary | null;
  /**
   * Live-stream judge wiring, or null when the scenario has no judged action.
   * Drives generic `*_judged` SSE listener registration and verdict-to-tool
   * attachment in the event stream, so no scenario names are hardcoded there.
   */
  liveJudge: LiveJudgeConfig | null;
  /**
   * Round-anchored scenario-specific timeline markers derived from the run's
   * `scenario_extras`. Each becomes a jump-to FAB on the run-detail page and a
   * divider in the chat pane. `extras` is `unknown`, narrowed internally to the
   * scenario's own variant. Default plug-in returns `[]`.
   */
  getTimelineMarkers: (args: { extras: unknown }) => ScenarioTimelineMarker[];
  /**
   * Classify a scenario-specific `RoundEnded.trigger` as success or failure so
   * the round-timeline badge can tone it, or null to fall back to the generic
   * `round_completed` / `round_failed` handling. Default plug-in returns null.
   */
  classifyRoundTrigger: (trigger: string) => RoundTriggerOutcome | null;
}
