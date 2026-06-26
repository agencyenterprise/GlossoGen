"use client";

import { NumberInput } from "../knobs-widgets/number-input";
import { Toggle } from "../knobs-widgets/toggle";
import { ContainerYardModeSelector } from "./container-yard-mode-selector";
import {
  getFieldError,
  type ContainerYardFieldError,
  type ContainerYardKnobsState,
  type ContainerYardMode,
} from "./container-yard-knobs-state";

const DEFAULT_MODE: ContainerYardMode = "single";

function SwapModeFields({
  state,
  errors,
  onChange,
}: {
  state: ContainerYardKnobsState;
  errors: ContainerYardFieldError[];
  onChange: (next: ContainerYardKnobsState) => void;
}) {
  const swapMax = state.round_count > 1 ? state.round_count - 1 : 1;
  return (
    <div className="space-y-4 rounded-md border border-border bg-muted/20 p-4">
      <h4 className="text-sm font-semibold">Swap-mode settings</h4>
      <NumberInput
        label="Swap round"
        description={`Round at which the two teams' crane operators swap. Must be between 1 and ${swapMax}.`}
        value={state.swap_round}
        onChange={next => onChange({ ...state, swap_round: next })}
        min={1}
        max={swapMax}
        step={1}
        unit="round"
        error={getFieldError({ errors, field: "swap_round" })}
        nullable={false}
        disabled={false}
      />
      <Toggle
        label="Announce swap to agents"
        description="If enabled, agents receive an in-channel notice when the swap fires."
        value={state.announce_swap}
        onChange={next => onChange({ ...state, announce_swap: next })}
        disabled={false}
      />
      <Toggle
        label="Postmortem channel remains available after swap"
        description="If enabled, swapped-in crane operators keep access to their new team's postmortem."
        value={state.postmortem_after_swap}
        onChange={next => onChange({ ...state, postmortem_after_swap: next })}
        disabled={!state.postmortem_enabled}
      />
    </div>
  );
}

function InternModeFields({
  state,
  errors,
  onChange,
}: {
  state: ContainerYardKnobsState;
  errors: ContainerYardFieldError[];
  onChange: (next: ContainerYardKnobsState) => void;
}) {
  const joinMax =
    state.intern_takeover_round !== null && state.intern_takeover_round > 1
      ? state.intern_takeover_round - 1
      : state.round_count;
  const takeoverMin = state.intern_join_round !== null ? state.intern_join_round + 1 : 2;
  return (
    <div className="space-y-4 rounded-md border border-border bg-muted/20 p-4">
      <h4 className="text-sm font-semibold">Intern-mode settings</h4>
      <NumberInput
        label="Intern join round"
        description="Round at which the silent intern joins the link channel and begins observing."
        value={state.intern_join_round}
        onChange={next => onChange({ ...state, intern_join_round: next })}
        min={1}
        max={joinMax}
        step={1}
        unit="round"
        error={getFieldError({ errors, field: "intern_join_round" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Intern takeover round"
        description={`Round at which the intern replaces the crane operator. Must be greater than join round and at most ${state.round_count}.`}
        value={state.intern_takeover_round}
        onChange={next => onChange({ ...state, intern_takeover_round: next })}
        min={takeoverMin}
        max={state.round_count}
        step={1}
        unit="round"
        error={getFieldError({ errors, field: "intern_takeover_round" })}
        nullable={false}
        disabled={false}
      />
    </div>
  );
}

function SharedSection({
  state,
  errors,
  onChange,
}: {
  state: ContainerYardKnobsState;
  errors: ContainerYardFieldError[];
  onChange: (next: ContainerYardKnobsState) => void;
}) {
  return (
    <div className="space-y-4 rounded-md border border-border bg-muted/20 p-4">
      <h4 className="text-sm font-semibold">Shared settings</h4>
      <NumberInput
        label="Round count"
        description="Total number of rounds the simulation will run."
        value={state.round_count}
        onChange={next =>
          onChange({ ...state, round_count: next === null ? state.round_count : next })
        }
        min={1}
        max={null}
        step={1}
        unit="rounds"
        error={getFieldError({ errors, field: "round_count" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Max round duration"
        description="Hard cap on wall-clock seconds a single round may take before the clock advances."
        value={state.max_round_duration_seconds}
        onChange={next =>
          onChange({
            ...state,
            max_round_duration_seconds: next === null ? state.max_round_duration_seconds : next,
          })
        }
        min={1}
        max={null}
        step={1}
        unit="seconds"
        error={getFieldError({ errors, field: "max_round_duration_seconds" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Round time budget"
        description="Per-round character budget on the link channel. One character = one simulated second."
        value={state.round_time_budget_seconds}
        onChange={next =>
          onChange({
            ...state,
            round_time_budget_seconds: next === null ? state.round_time_budget_seconds : next,
          })
        }
        min={1}
        max={null}
        step={1}
        unit="seconds"
        error={getFieldError({ errors, field: "round_time_budget_seconds" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Batch size"
        description="Number of inbound containers to sort each round. More containers raise the per-round message entropy, so the budget binds harder."
        value={state.batch_size}
        onChange={next =>
          onChange({ ...state, batch_size: next === null ? state.batch_size : next })
        }
        min={1}
        max={null}
        step={1}
        unit="containers"
        error={getFieldError({ errors, field: "batch_size" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Yard slot count"
        description="Number of slots in the yard. Must hold the batch plus its target bays (≥ 2 × batch size + 2)."
        value={state.yard_slot_count}
        onChange={next =>
          onChange({ ...state, yard_slot_count: next === null ? state.yard_slot_count : next })
        }
        min={4}
        max={null}
        step={1}
        unit="slots"
        error={getFieldError({ errors, field: "yard_slot_count" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Channel noise level"
        description="Per-character drop probability on the link channel. 0.0 = lossless. Dropped characters become `_`."
        value={state.channel_noise_level}
        onChange={next =>
          onChange({
            ...state,
            channel_noise_level: next === null ? state.channel_noise_level : next,
          })
        }
        min={0}
        max={1}
        step={0.05}
        unit={null}
        error={getFieldError({ errors, field: "channel_noise_level" })}
        nullable={false}
        disabled={false}
      />
      <NumberInput
        label="Random seed"
        description="Controls the case shuffle for each round."
        value={state.seed}
        onChange={next => onChange({ ...state, seed: next === null ? state.seed : next })}
        min={null}
        max={null}
        step={1}
        unit={null}
        error={null}
        nullable={false}
        disabled={false}
      />
      <Toggle
        label="Postmortem enabled"
        description="Adds a shared postmortem discussion phase after each round."
        value={state.postmortem_enabled}
        onChange={next => onChange({ ...state, postmortem_enabled: next })}
        disabled={false}
      />
    </div>
  );
}

export function ContainerYardKnobsForm({
  state,
  errors,
  onChange,
}: {
  state: ContainerYardKnobsState | null;
  errors: ContainerYardFieldError[];
  onChange: (next: ContainerYardKnobsState) => void;
}) {
  const activeMode: ContainerYardMode = state ? state.mode : DEFAULT_MODE;

  if (!state) {
    return <div className="text-xs text-muted-foreground">Loading container-yard defaults...</div>;
  }

  function handleMode(nextMode: ContainerYardMode) {
    if (!state || state.mode === nextMode) {
      return;
    }
    const next: ContainerYardKnobsState = { ...state, mode: nextMode };
    if (nextMode === "swap" && next.swap_round === null) {
      next.swap_round = Math.max(1, Math.floor(state.round_count / 2));
    }
    if (nextMode === "intern") {
      if (next.intern_join_round === null) {
        next.intern_join_round = Math.max(1, Math.floor(state.round_count / 4));
      }
      if (next.intern_takeover_round === null) {
        next.intern_takeover_round = Math.max(
          next.intern_join_round + 1,
          Math.floor((state.round_count * 2) / 3)
        );
      }
    }
    onChange(next);
  }

  return (
    <div className="space-y-6">
      <ContainerYardModeSelector selected={activeMode} onChange={handleMode} disabled={false} />

      {activeMode === "swap" ? (
        <SwapModeFields state={state} errors={errors} onChange={onChange} />
      ) : null}
      {activeMode === "intern" ? (
        <InternModeFields state={state} errors={errors} onChange={onChange} />
      ) : null}

      <SharedSection state={state} errors={errors} onChange={onChange} />
    </div>
  );
}
