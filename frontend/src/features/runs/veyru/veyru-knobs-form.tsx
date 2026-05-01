"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { api } from "@/shared/lib/api-client";
import { ModelPicker } from "../model-picker";
import { NumberInput } from "../knobs-widgets/number-input";
import { Toggle } from "../knobs-widgets/toggle";
import { VeyruModeSelector } from "./veyru-mode-selector";
import {
  getFieldError,
  knobsToState,
  mergePresetIntoState,
  VEYRU_MODE_TO_PRESET,
  type VeyruFieldError,
  type VeyruKnobsState,
  type VeyruMode,
} from "./veyru-knobs-state";

const VEYRU_SCENARIO = "veyru";
const DEFAULT_MODE: VeyruMode = "single";

type ModelOption = { model_prefix: string; provider: string };

function VeyruSwapModeFields({
  state,
  errors,
  onChange,
}: {
  state: VeyruKnobsState;
  errors: VeyruFieldError[];
  onChange: (next: VeyruKnobsState) => void;
}) {
  const swapMax = state.round_count > 1 ? state.round_count - 1 : 1;
  return (
    <div className="space-y-4 rounded-md border border-border bg-muted/20 p-4">
      <h4 className="text-sm font-semibold">Swap-mode settings</h4>
      <NumberInput
        label="Swap round"
        description={`Round at which the two teams' field observers swap. Must be between 1 and ${swapMax}.`}
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
        description="If enabled, agents receive an in-channel notice and next-round injection about the swap."
        value={state.announce_swap}
        onChange={next => onChange({ ...state, announce_swap: next })}
        disabled={false}
      />
      <Toggle
        label="Postmortem channel remains available after swap"
        description="If enabled, observers joining a new team keep access to that team's postmortem channel."
        value={state.postmortem_after_swap}
        onChange={next => onChange({ ...state, postmortem_after_swap: next })}
        disabled={!state.postmortem_enabled}
      />
    </div>
  );
}

function VeyruInternModeFields({
  state,
  errors,
  onChange,
}: {
  state: VeyruKnobsState;
  errors: VeyruFieldError[];
  onChange: (next: VeyruKnobsState) => void;
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
        description="Round at which the silent intern joins the comm link and begins observing."
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
        description={`Round at which the intern replaces the field observer. Must be greater than join round and at most ${state.round_count}.`}
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
      <Toggle
        label="Intern keeps postmortem access after takeover"
        description="If enabled, the intern joins the postmortem channel when they take over as field observer."
        value={state.postmortem_after_swap}
        onChange={next => onChange({ ...state, postmortem_after_swap: next })}
        disabled={!state.postmortem_enabled}
      />
    </div>
  );
}

function SharedSection({
  state,
  errors,
  models,
  onChange,
}: {
  state: VeyruKnobsState;
  errors: VeyruFieldError[];
  models: ModelOption[];
  onChange: (next: VeyruKnobsState) => void;
}) {
  function handleJudgeModel(selectedModel: string, selectedProvider: string) {
    onChange({ ...state, judge_model: selectedModel, judge_provider: selectedProvider });
  }

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
        description="Fixed per-round time budget. One character of communication costs one simulated second."
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
        label="Channel noise level"
        description="Per-character drop probability on the comm link channel(s) (postmortem stays clean). 0.0 = lossless, 1.0 = every character dropped. Dropped characters are replaced with `_`."
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
        description="Controls the shuffle of failure motifs into round cases."
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
      <div className="space-y-1">
        <span className="block text-sm font-medium">Judge LLM</span>
        <p className="text-xs text-muted-foreground">
          Model used to evaluate whether stabilization actions match the Veyru&apos;s needs.
        </p>
        <ModelPicker
          label="Judge model"
          models={models}
          selectedModel={state.judge_model}
          onSelect={handleJudgeModel}
        />
        <p className="text-[11px] text-muted-foreground">
          Selected provider: <span className="font-mono">{state.judge_provider}</span>
        </p>
      </div>
    </div>
  );
}

export function VeyruKnobsForm({
  state,
  models,
  errors,
  onChange,
}: {
  state: VeyruKnobsState | null;
  models: ModelOption[];
  errors: VeyruFieldError[];
  onChange: (next: VeyruKnobsState) => void;
}) {
  const appliedPresetsRef = useRef<Set<VeyruMode>>(new Set());

  const activeMode: VeyruMode = state ? state.mode : DEFAULT_MODE;
  const presetName = VEYRU_MODE_TO_PRESET[activeMode];

  const presetQuery = useQuery({
    queryKey: ["veyru-preset", presetName],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/scenarios/{scenario_name}/knobs/{knobs_name}", {
        params: { path: { scenario_name: VEYRU_SCENARIO, knobs_name: presetName } },
      });
      if (error) {
        throw new Error("Failed to fetch preset");
      }
      return data;
    },
  });

  const presetKnobs = presetQuery.data?.knobs;

  useEffect(() => {
    if (!presetKnobs) {
      return;
    }
    if (appliedPresetsRef.current.has(activeMode)) {
      return;
    }
    appliedPresetsRef.current.add(activeMode);
    const presetState = knobsToState(presetKnobs as Record<string, unknown>);
    if (!state) {
      onChange(presetState);
      return;
    }
    if (state.mode !== activeMode) {
      return;
    }
    const merged = mergePresetIntoState({ previous: state, preset: presetState });
    onChange(merged);
  }, [activeMode, presetKnobs, state, onChange]);

  if (!state) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading Veyru defaults...
      </div>
    );
  }

  function handleMode(nextMode: VeyruMode) {
    if (!state || state.mode === nextMode) {
      return;
    }
    const next: VeyruKnobsState = { ...state, mode: nextMode };
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
      <VeyruModeSelector selected={state.mode} onChange={handleMode} disabled={false} />

      {state.mode === "swap" ? (
        <VeyruSwapModeFields state={state} errors={errors} onChange={onChange} />
      ) : null}
      {state.mode === "intern" ? (
        <VeyruInternModeFields state={state} errors={errors} onChange={onChange} />
      ) : null}

      <SharedSection state={state} errors={errors} models={models} onChange={onChange} />
    </div>
  );
}
