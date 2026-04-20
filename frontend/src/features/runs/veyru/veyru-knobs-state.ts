import type { AgentModelOverride } from "../agent-model-overrides";

export type VeyruMode = "single" | "swap" | "intern";

export type VeyruKnobsState = {
  mode: VeyruMode;
  round_count: number;
  seconds_per_character: number;
  seed: number;
  postmortem_enabled: boolean;
  max_round_duration_seconds: number;
  judge_model: string;
  judge_provider: string;
  swap_round: number | null;
  announce_swap: boolean;
  intern_join_round: number | null;
  intern_takeover_round: number | null;
  postmortem_after_swap: boolean;
};

export type VeyruFieldError = {
  field: keyof VeyruKnobsState;
  message: string;
};

export const VEYRU_MODE_TO_PRESET: Record<VeyruMode, string> = {
  single: "knobs_default",
  swap: "knobs_two_team_swap",
  intern: "knobs_intern",
};

function coerceNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return fallback;
}

function coerceNullableNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function coerceBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") {
    return value;
  }
  return fallback;
}

function coerceString(value: unknown, fallback: string): string {
  if (typeof value === "string") {
    return value;
  }
  return fallback;
}

export function detectMode(knobs: Record<string, unknown>): VeyruMode {
  if (coerceBool(knobs.intern_enabled, false)) {
    return "intern";
  }
  if (coerceBool(knobs.two_teams, false)) {
    return "swap";
  }
  return "single";
}

export function knobsToState(knobs: Record<string, unknown>): VeyruKnobsState {
  return {
    mode: detectMode(knobs),
    round_count: coerceNumber(knobs.round_count, 12),
    seconds_per_character: coerceNumber(knobs.seconds_per_character, 2.0),
    seed: coerceNumber(knobs.seed, 42),
    postmortem_enabled: coerceBool(knobs.postmortem_enabled, true),
    max_round_duration_seconds: coerceNumber(knobs.max_round_duration_seconds, 300),
    judge_model: coerceString(knobs.judge_model, "claude-haiku-4-5-20251001"),
    judge_provider: coerceString(knobs.judge_provider, "anthropic"),
    swap_round: coerceNullableNumber(knobs.swap_round),
    announce_swap: coerceBool(knobs.announce_swap, false),
    intern_join_round: coerceNullableNumber(knobs.intern_join_round),
    intern_takeover_round: coerceNullableNumber(knobs.intern_takeover_round),
    postmortem_after_swap: coerceBool(knobs.postmortem_after_swap, true),
  };
}

export function mergePresetIntoState({
  previous,
  preset,
}: {
  previous: VeyruKnobsState;
  preset: VeyruKnobsState;
}): VeyruKnobsState {
  return {
    mode: preset.mode,
    round_count: previous.round_count,
    seconds_per_character: previous.seconds_per_character,
    seed: previous.seed,
    postmortem_enabled: previous.postmortem_enabled,
    max_round_duration_seconds: previous.max_round_duration_seconds,
    judge_model: previous.judge_model,
    judge_provider: previous.judge_provider,
    swap_round: preset.swap_round,
    announce_swap: preset.announce_swap,
    intern_join_round: preset.intern_join_round,
    intern_takeover_round: preset.intern_takeover_round,
    postmortem_after_swap: preset.postmortem_after_swap,
  };
}

export function validateState(state: VeyruKnobsState): VeyruFieldError[] {
  const errors: VeyruFieldError[] = [];
  if (state.round_count < 1) {
    errors.push({ field: "round_count", message: "Round count must be at least 1." });
  }
  if (state.max_round_duration_seconds < 1) {
    errors.push({
      field: "max_round_duration_seconds",
      message: "Round duration must be at least 1 second.",
    });
  }
  if (state.seconds_per_character < 0) {
    errors.push({
      field: "seconds_per_character",
      message: "Seconds per character must be non-negative.",
    });
  }
  if (state.mode === "swap") {
    if (state.swap_round === null) {
      errors.push({ field: "swap_round", message: "Swap round is required for Swap mode." });
    } else if (state.swap_round < 1) {
      errors.push({ field: "swap_round", message: "Swap round must be at least 1." });
    } else if (state.swap_round >= state.round_count) {
      errors.push({
        field: "swap_round",
        message: `Swap round must be less than round count (${state.round_count}).`,
      });
    }
  }
  if (state.mode === "intern") {
    if (state.intern_join_round === null) {
      errors.push({
        field: "intern_join_round",
        message: "Intern join round is required for Intern mode.",
      });
    } else if (state.intern_join_round < 1) {
      errors.push({
        field: "intern_join_round",
        message: "Intern join round must be at least 1.",
      });
    }
    if (state.intern_takeover_round === null) {
      errors.push({
        field: "intern_takeover_round",
        message: "Intern takeover round is required for Intern mode.",
      });
    } else if (
      state.intern_join_round !== null &&
      state.intern_takeover_round <= state.intern_join_round
    ) {
      errors.push({
        field: "intern_takeover_round",
        message: "Takeover round must be greater than join round.",
      });
    } else if (state.intern_takeover_round > state.round_count) {
      errors.push({
        field: "intern_takeover_round",
        message: `Takeover round must be at most round count (${state.round_count}).`,
      });
    }
  }
  return errors;
}

export function getFieldError({
  errors,
  field,
}: {
  errors: VeyruFieldError[];
  field: keyof VeyruKnobsState;
}): string | null {
  const hit = errors.find(e => e.field === field);
  if (hit) {
    return hit.message;
  }
  return null;
}

export function buildPayload({
  state,
  modelOverrides,
}: {
  state: VeyruKnobsState;
  modelOverrides: Record<string, AgentModelOverride>;
}): Record<string, unknown> {
  const twoTeams = state.mode === "swap";
  const internEnabled = state.mode === "intern";
  const swapRound = twoTeams ? state.swap_round : null;
  const internJoinRound = internEnabled ? state.intern_join_round : null;
  const internTakeoverRound = internEnabled ? state.intern_takeover_round : null;

  const overridesPayload: Record<string, { model: string; provider: string }> = {};
  for (const [agentId, ov] of Object.entries(modelOverrides)) {
    overridesPayload[agentId] = { model: ov.model, provider: ov.provider };
  }

  return {
    announce_swap: state.announce_swap,
    intern_enabled: internEnabled,
    intern_join_round: internJoinRound,
    intern_takeover_round: internTakeoverRound,
    judge_model: state.judge_model,
    judge_provider: state.judge_provider,
    max_round_duration_seconds: state.max_round_duration_seconds,
    model_overrides: overridesPayload,
    postmortem_after_swap: state.postmortem_after_swap,
    postmortem_enabled: state.postmortem_enabled,
    round_count: state.round_count,
    seconds_per_character: state.seconds_per_character,
    seed: state.seed,
    swap_round: swapRound,
    two_teams: twoTeams,
  };
}
