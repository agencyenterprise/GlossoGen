"use client";

import { useMemo } from "react";
import { Plus, Trash2 } from "lucide-react";
import { ModelPicker } from "./model-picker";

export type ChannelVisibilityKind = "full" | "none" | "from_round";

export type ChannelVisibility =
  | { kind: "full" }
  | { kind: "none" }
  | { kind: "from_round"; round_floor: number };

export type SwapAgentEvent = {
  type: "swap_agent";
  at_round: number;
  agent_id: string;
  model: string;
  provider: string;
  channel_visibility: Record<string, ChannelVisibility>;
};

export type SetPostmortemEvent = {
  type: "set_postmortem";
  at_round: number;
  enabled: boolean;
};

export type ScheduledEvent = SwapAgentEvent | SetPostmortemEvent;

export type AgentInfo = {
  agent_id: string;
  role_name: string;
  channels: string[];
};

export type ModelInfo = {
  model_prefix: string;
  provider: string;
};

type VisibilityOption = "full" | "none" | "from_previous_phase" | "from_specific_round";

type PhaseDraft = {
  duration: number;
  swap: {
    agent_id: string;
    model: string;
    provider: string;
    visibility_options: Record<string, { option: VisibilityOption; specific_round: number | null }>;
  } | null;
  disable_postmortem: boolean;
};

export type PhaseBuilderState = {
  phase_zero_duration: number;
  phases: PhaseDraft[];
};

export function emptyPhaseBuilderState(): PhaseBuilderState {
  return { phase_zero_duration: 15, phases: [] };
}

export function computeRoundCount(state: PhaseBuilderState): number {
  return state.phase_zero_duration + state.phases.reduce((sum, phase) => sum + phase.duration, 0);
}

function phaseBoundaryRound(state: PhaseBuilderState, phaseIndex: number): number {
  let round = state.phase_zero_duration + 1;
  for (let i = 0; i < phaseIndex; i++) {
    const phase = state.phases[i];
    if (phase !== undefined) {
      round += phase.duration;
    }
  }
  return round;
}

function previousPhaseStart(state: PhaseBuilderState, phaseIndex: number): number {
  if (phaseIndex === 0) {
    return 1;
  }
  return phaseBoundaryRound(state, phaseIndex - 1);
}

export function buildScheduledEvents(state: PhaseBuilderState): ScheduledEvent[] {
  const events: ScheduledEvent[] = [];
  let postmortemAlreadyDisabled = false;
  state.phases.forEach((phase, phaseIndex) => {
    const at_round = phaseBoundaryRound(state, phaseIndex);
    if (phase.disable_postmortem && !postmortemAlreadyDisabled) {
      events.push({ type: "set_postmortem", at_round, enabled: false });
      postmortemAlreadyDisabled = true;
    }
    if (phase.swap !== null) {
      const channel_visibility: Record<string, ChannelVisibility> = {};
      Object.entries(phase.swap.visibility_options).forEach(([channelId, opt]) => {
        if (opt.option === "full") {
          channel_visibility[channelId] = { kind: "full" };
        } else if (opt.option === "none") {
          channel_visibility[channelId] = { kind: "none" };
        } else if (opt.option === "from_previous_phase") {
          channel_visibility[channelId] = {
            kind: "from_round",
            round_floor: previousPhaseStart(state, phaseIndex),
          };
        } else if (opt.option === "from_specific_round" && opt.specific_round !== null) {
          channel_visibility[channelId] = {
            kind: "from_round",
            round_floor: opt.specific_round,
          };
        }
      });
      events.push({
        type: "swap_agent",
        at_round,
        agent_id: phase.swap.agent_id,
        model: phase.swap.model,
        provider: phase.swap.provider,
        channel_visibility,
      });
    }
  });
  return events;
}

export function validatePhaseBuilder(state: PhaseBuilderState): string[] {
  const errors: string[] = [];
  if (state.phase_zero_duration < 1) {
    errors.push("Phase 0 duration must be at least 1 round.");
  }
  state.phases.forEach((phase, index) => {
    const phaseLabel = `Phase ${index + 1}`;
    if (phase.duration < 1) {
      errors.push(`${phaseLabel} duration must be at least 1 round.`);
    }
    if (phase.swap !== null) {
      if (!phase.swap.agent_id) {
        errors.push(`${phaseLabel}: select which agent to replace.`);
      }
      if (!phase.swap.model || !phase.swap.provider) {
        errors.push(`${phaseLabel}: pick a model for the new agent.`);
      }
      const boundary = phaseBoundaryRound(state, index);
      Object.entries(phase.swap.visibility_options).forEach(([channelId, opt]) => {
        if (opt.option === "from_specific_round" && opt.specific_round !== null) {
          if (opt.specific_round < 1 || opt.specific_round > boundary) {
            errors.push(
              `${phaseLabel}: ${channelId} round_floor must be between 1 and ${boundary}.`
            );
          }
        }
      });
    }
  });
  return errors;
}

export function PhaseBuilder({
  state,
  onChange,
  agents,
  models,
  scenarioHasPostmortem,
}: {
  state: PhaseBuilderState;
  onChange: (next: PhaseBuilderState) => void;
  agents: AgentInfo[];
  models: ModelInfo[];
  scenarioHasPostmortem: boolean;
}) {
  const totalRounds = computeRoundCount(state);
  const postmortemAlreadyDisabled = useMemo(() => {
    const flags: boolean[] = [];
    let disabled = false;
    state.phases.forEach(phase => {
      flags.push(disabled);
      if (phase.disable_postmortem) {
        disabled = true;
      }
    });
    return flags;
  }, [state.phases]);

  function updatePhase(index: number, mutator: (draft: PhaseDraft) => PhaseDraft) {
    const next = [...state.phases];
    const target = next[index];
    if (target === undefined) {
      return;
    }
    next[index] = mutator(target);
    onChange({ ...state, phases: next });
  }

  function addPhase() {
    onChange({
      ...state,
      phases: [
        ...state.phases,
        {
          duration: 15,
          swap: null,
          disable_postmortem: false,
        },
      ],
    });
  }

  function removePhase(index: number) {
    onChange({
      ...state,
      phases: state.phases.filter((_, i) => i !== index),
    });
  }

  return (
    <div className="space-y-3">
      <div className="rounded border border-border bg-muted/20 px-3 py-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Phase 0 (initial)</span>
          <span className="text-xs text-muted-foreground">
            rounds 1..{state.phase_zero_duration}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs">
          <label htmlFor="phase-zero-duration" className="text-muted-foreground">
            Duration (rounds):
          </label>
          <input
            id="phase-zero-duration"
            type="number"
            min={1}
            value={state.phase_zero_duration}
            onChange={e =>
              onChange({
                ...state,
                phase_zero_duration: Math.max(1, parseInt(e.target.value, 10) || 1),
              })
            }
            className="w-20 rounded border border-input bg-background px-2 py-1 text-xs"
          />
          <span className="text-muted-foreground">
            (original agents from the scenario; configure their models above)
          </span>
        </div>
      </div>

      {state.phases.map((phase, index) => (
        <PhaseCard
          key={index}
          phase={phase}
          phaseIndex={index}
          boundaryRound={phaseBoundaryRound(state, index)}
          previousPhaseStart={previousPhaseStart(state, index)}
          agents={agents}
          models={models}
          scenarioHasPostmortem={scenarioHasPostmortem}
          postmortemAlreadyDisabled={postmortemAlreadyDisabled[index] ?? false}
          onChange={mutator => updatePhase(index, mutator)}
          onRemove={() => removePhase(index)}
        />
      ))}

      <div className="flex items-center justify-between pt-1">
        <button
          type="button"
          onClick={addPhase}
          className="inline-flex items-center gap-1.5 rounded border border-dashed border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" />
          Add phase
        </button>
        <span className="text-xs text-muted-foreground">
          Total round_count: <span className="font-medium text-foreground">{totalRounds}</span>
        </span>
      </div>
    </div>
  );
}

function PhaseCard({
  phase,
  phaseIndex,
  boundaryRound,
  previousPhaseStart,
  agents,
  models,
  scenarioHasPostmortem,
  postmortemAlreadyDisabled,
  onChange,
  onRemove,
}: {
  phase: PhaseDraft;
  phaseIndex: number;
  boundaryRound: number;
  previousPhaseStart: number;
  agents: AgentInfo[];
  models: ModelInfo[];
  scenarioHasPostmortem: boolean;
  postmortemAlreadyDisabled: boolean;
  onChange: (mutator: (draft: PhaseDraft) => PhaseDraft) => void;
  onRemove: () => void;
}) {
  const swap = phase.swap;
  const selectedAgent = swap !== null ? agents.find(a => a.agent_id === swap.agent_id) : null;
  const channels = selectedAgent?.channels ?? [];

  function setAgent(agent_id: string) {
    onChange(draft => {
      const visibility_options: Record<
        string,
        { option: VisibilityOption; specific_round: number | null }
      > = {};
      const agent = agents.find(a => a.agent_id === agent_id);
      (agent?.channels ?? []).forEach(ch => {
        visibility_options[ch] = { option: "full", specific_round: null };
      });
      return {
        ...draft,
        swap: {
          agent_id,
          model: draft.swap?.model ?? "",
          provider: draft.swap?.provider ?? "",
          visibility_options,
        },
      };
    });
  }

  function setModel(model: string, provider: string) {
    onChange(draft =>
      draft.swap === null ? draft : { ...draft, swap: { ...draft.swap, model, provider } }
    );
  }

  function setVisibility(channelId: string, option: VisibilityOption) {
    onChange(draft => {
      if (draft.swap === null) {
        return draft;
      }
      const next_options = { ...draft.swap.visibility_options };
      const previous = next_options[channelId] ?? { option: "full", specific_round: null };
      next_options[channelId] = {
        option,
        specific_round: option === "from_specific_round" ? (previous.specific_round ?? 1) : null,
      };
      return { ...draft, swap: { ...draft.swap, visibility_options: next_options } };
    });
  }

  function setSpecificRound(channelId: string, value: number) {
    onChange(draft => {
      if (draft.swap === null) {
        return draft;
      }
      const next_options = { ...draft.swap.visibility_options };
      const previous = next_options[channelId];
      if (previous === undefined) {
        return draft;
      }
      next_options[channelId] = { ...previous, specific_round: value };
      return { ...draft, swap: { ...draft.swap, visibility_options: next_options } };
    });
  }

  function toggleSwap() {
    onChange(draft =>
      draft.swap === null
        ? {
            ...draft,
            swap: { agent_id: "", model: "", provider: "", visibility_options: {} },
          }
        : { ...draft, swap: null }
    );
  }

  return (
    <div className="rounded border border-border bg-muted/20 px-3 py-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">
          Phase {phaseIndex + 1} (boundary at round {boundaryRound})
        </span>
        <button
          type="button"
          onClick={onRemove}
          className="text-muted-foreground transition-colors hover:text-destructive"
          title="Remove phase"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="mt-2 flex items-center gap-2 text-xs">
        <label className="text-muted-foreground">Duration (rounds):</label>
        <input
          type="number"
          min={1}
          value={phase.duration}
          onChange={e =>
            onChange(draft => ({
              ...draft,
              duration: Math.max(1, parseInt(e.target.value, 10) || 1),
            }))
          }
          className="w-20 rounded border border-input bg-background px-2 py-1 text-xs"
        />
      </div>

      <div className="mt-2 flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          id={`phase-${phaseIndex}-swap`}
          checked={phase.swap !== null}
          onChange={toggleSwap}
        />
        <label htmlFor={`phase-${phaseIndex}-swap`} className="text-muted-foreground">
          Replace an agent at this boundary
        </label>
      </div>

      {swap !== null ? (
        <div className="mt-2 space-y-2 border-l-2 border-border pl-3">
          <div className="flex items-center gap-2 text-xs">
            <label className="text-muted-foreground">Replace:</label>
            <select
              value={swap.agent_id}
              onChange={e => setAgent(e.target.value)}
              className="rounded border border-input bg-background px-2 py-1 text-xs"
            >
              <option value="">Select an agent...</option>
              {agents.map(a => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.role_name}
                </option>
              ))}
            </select>
          </div>

          {swap.agent_id ? (
            <div>
              <ModelPicker
                label="Model for the new agent"
                models={models}
                selectedModel={swap.model}
                onSelect={(model, provider) => setModel(model, provider)}
              />
            </div>
          ) : null}

          {channels.length > 0 ? (
            <div className="space-y-1">
              <span className="text-[11px] text-muted-foreground">Channel visibility</span>
              {channels.map(channelId => {
                const current = swap.visibility_options[channelId] ?? {
                  option: "full" as VisibilityOption,
                  specific_round: null,
                };
                return (
                  <div key={channelId} className="flex items-center gap-2 text-xs">
                    <span className="w-24 font-mono text-muted-foreground">{channelId}</span>
                    <select
                      value={current.option}
                      onChange={e => setVisibility(channelId, e.target.value as VisibilityOption)}
                      className="rounded border border-input bg-background px-2 py-1 text-xs"
                    >
                      <option value="full">Full</option>
                      <option value="none">Hidden</option>
                      {phaseIndex > 0 ? (
                        <option value="from_previous_phase">
                          From start of previous phase (round {previousPhaseStart})
                        </option>
                      ) : null}
                      <option value="from_specific_round">From specific round...</option>
                    </select>
                    {current.option === "from_specific_round" ? (
                      <input
                        type="number"
                        min={1}
                        max={boundaryRound}
                        value={current.specific_round ?? 1}
                        onChange={e =>
                          setSpecificRound(
                            channelId,
                            Math.max(1, parseInt(e.target.value, 10) || 1)
                          )
                        }
                        className="w-20 rounded border border-input bg-background px-2 py-1 text-xs"
                      />
                    ) : null}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      {scenarioHasPostmortem ? (
        <div className="mt-2 flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            id={`phase-${phaseIndex}-postmortem`}
            checked={phase.disable_postmortem}
            disabled={postmortemAlreadyDisabled}
            onChange={e => onChange(draft => ({ ...draft, disable_postmortem: e.target.checked }))}
          />
          <label
            htmlFor={`phase-${phaseIndex}-postmortem`}
            className={
              postmortemAlreadyDisabled ? "text-muted-foreground/60" : "text-muted-foreground"
            }
            title={postmortemAlreadyDisabled ? "Already disabled in an earlier phase" : undefined}
          >
            Disable postmortem at this phase
          </label>
        </div>
      ) : null}
    </div>
  );
}
