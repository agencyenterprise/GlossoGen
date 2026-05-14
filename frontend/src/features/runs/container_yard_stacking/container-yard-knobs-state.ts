import type { AgentModelOverride } from "../agent-model-overrides";

export type ContainerYardMode = "single" | "swap" | "intern";

export type ContainerYardKnobsState = {
  mode: ContainerYardMode;
  round_count: number;
  time_budget_seconds: number;
  seed: number;
  postmortem_enabled: boolean;
  postmortem_disabled_at_start: boolean;
  max_round_duration_seconds: number;
  swap_round: number | null;
  announce_swap: boolean;
  postmortem_after_swap: boolean;
  intern_join_round: number | null;
  intern_takeover_round: number | null;
  channel_noise_level: number;
};

export type ContainerYardFieldError = {
  field: keyof ContainerYardKnobsState;
  message: string;
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

export function detectMode(knobs: Record<string, unknown>): ContainerYardMode {
  if (coerceBool(knobs.intern_enabled, false)) {
    return "intern";
  }
  if (coerceBool(knobs.two_teams, false)) {
    return "swap";
  }
  return "single";
}

export function knobsToState(knobs: Record<string, unknown>): ContainerYardKnobsState {
  return {
    mode: detectMode(knobs),
    round_count: coerceNumber(knobs.round_count, 15),
    time_budget_seconds: coerceNumber(knobs.time_budget_seconds, 200),
    seed: coerceNumber(knobs.seed, 42),
    postmortem_enabled: coerceBool(knobs.postmortem_enabled, true),
    postmortem_disabled_at_start: coerceBool(knobs.postmortem_disabled_at_start, false),
    max_round_duration_seconds: coerceNumber(knobs.max_round_duration_seconds, 300),
    swap_round: coerceNullableNumber(knobs.swap_round),
    announce_swap: coerceBool(knobs.announce_swap, false),
    postmortem_after_swap: coerceBool(knobs.postmortem_after_swap, true),
    intern_join_round: coerceNullableNumber(knobs.intern_join_round),
    intern_takeover_round: coerceNullableNumber(knobs.intern_takeover_round),
    channel_noise_level: coerceNumber(knobs.channel_noise_level, 0.0),
  };
}

export function validateState(state: ContainerYardKnobsState): ContainerYardFieldError[] {
  const errors: ContainerYardFieldError[] = [];
  if (state.round_count < 1) {
    errors.push({ field: "round_count", message: "Round count must be at least 1." });
  }
  if (state.max_round_duration_seconds < 1) {
    errors.push({
      field: "max_round_duration_seconds",
      message: "Round duration must be at least 1 second.",
    });
  }
  if (state.time_budget_seconds < 1) {
    errors.push({
      field: "time_budget_seconds",
      message: "Round time budget must be at least 1 second.",
    });
  }
  if (state.channel_noise_level < 0 || state.channel_noise_level > 1) {
    errors.push({
      field: "channel_noise_level",
      message: "Channel noise level must be between 0 and 1.",
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
  errors: ContainerYardFieldError[];
  field: keyof ContainerYardKnobsState;
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
  state: ContainerYardKnobsState;
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
    channel_noise_level: state.channel_noise_level,
    intern_enabled: internEnabled,
    intern_join_round: internJoinRound,
    intern_takeover_round: internTakeoverRound,
    max_round_duration_seconds: state.max_round_duration_seconds,
    model_overrides: overridesPayload,
    postmortem_after_swap: state.postmortem_after_swap,
    postmortem_disabled_at_start: state.postmortem_disabled_at_start,
    postmortem_enabled: state.postmortem_enabled,
    round_count: state.round_count,
    seed: state.seed,
    swap_round: swapRound,
    time_budget_seconds: state.time_budget_seconds,
    two_teams: twoTeams,
  };
}
